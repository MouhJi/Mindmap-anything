"""Run the labeled synthetic regression evaluation without an LLM or database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .expansion import ExpansionService
from .ingestion import KnowledgePipeline
from .models import ExtractedEntity, ExtractedRelationship, ExtractionResult, SourceChunk, name_key, stable_id
from .repository import InMemoryRepository


def evaluate_sample(path: Path | None = None) -> dict:
    path = path or Path(__file__).parent / "evaluation/sample.json"
    dataset = json.loads(path.read_text(encoding="utf-8"))
    store = InMemoryRepository()
    pipeline = KnowledgePipeline(store)
    entities = [ExtractedEntity.model_validate(item) for item in dataset["entities"]]
    decisions, useful_edge_ids, raw_edge_keys = [], set(), []
    for record in dataset["records"]:
        source = SourceChunk(
            project_id="evaluation", chunk_id=record["id"], document_id="synthetic-doc",
            url="https://docs.example/synthetic", text=record["text"], topic=dataset["center"],
        )
        extracted = ExtractedRelationship(
            source=record["source"], target=record["target"], relation_type=record["relation_type"],
            evidence=record.get("evidence", record["text"]),
            chunk_id=record.get("referenced_chunk", record["id"]),
        )
        result = ExtractionResult(entities=entities, relationships=[extracted])
        report = pipeline.ingest_chunk(source, result)
        decision = report.decisions[0]
        decisions.append({"id": record["id"], "accepted": decision.accepted,
                          "expected_accepted": record["expected_accepted"], "reasons": decision.reasons})
        if decision.accepted:
            def resolve(name):
                matches = [item for item in store.entities.values()
                           if name_key(name) in {name_key(item.canonical_name), *map(name_key, item.aliases)}]
                if len(matches) != 1:
                    raise ValueError("Evaluation endpoint is ambiguous: " + name)
                return matches[0].entity_id
            key = (resolve(record["source"]), record["relation_type"], resolve(record["target"]))
            raw_edge_keys.append(key)
            if record["useful"]:
                useful_edge_ids.add(stable_id("rel", "evaluation", *key))

    duplicate_entities = 0
    entity_groups = {}
    for group in dataset["canonical_groups"]:
        group_keys = set(map(name_key, group))
        matches = {item.entity_id for item in store.entities.values()
                   if group_keys & {name_key(item.canonical_name), *map(name_key, item.aliases)}}
        duplicate_entities += max(0, len(matches) - 1)
        for identifier in matches:
            entity_groups[identifier] = entity_groups.get(identifier, 0) + 1
    logical_edges = [(edge.source_id, edge.relation_type, edge.target_id) for edge in store.relationships.values()]
    accepted = [decision for decision in decisions if decision["accepted"]]
    correct = sum(decision["expected_accepted"] for decision in accepted)
    center = next(item for item in store.entities.values() if item.canonical_name == dataset["center"])
    expanded = ExpansionService(store).expand("evaluation", center.entity_id)
    precision_at_5 = sum(edge.id in useful_edge_ids for edge in expanded.edges) / 5
    return {
        "dataset": dataset["description"], "sample_relationships": len(decisions),
        "canonical_entities": len(store.entities), "canonical_relationships": len(logical_edges),
        "duplicate_entity_rate": duplicate_entities / max(1, len(store.entities)),
        "incorrect_entity_merges": sum(count > 1 for count in entity_groups.values()),
        "duplicate_relationship_rate": (len(logical_edges) - len(set(logical_edges))) / max(1, len(logical_edges)),
        "raw_accepted_duplicate_relationship_rate": (len(raw_edge_keys) - len(set(raw_edge_keys))) / max(1, len(raw_edge_keys)),
        "evidence_validation_pass_rate": len(accepted) / max(1, len(decisions)),
        "accepted_relationship_precision": correct / max(1, len(accepted)),
        "expansion_precision_at_5": precision_at_5,
        "label_agreement": sum(item["accepted"] == item["expected_accepted"] for item in decisions) / len(decisions),
        "decisions": decisions,
        "unfiltered_neighbors": sorted({
            store.entities[("evaluation", edge.target_id if edge.source_id == center.entity_id else edge.source_id)].canonical_name
            for edge in store.relationships.values() if center.entity_id in {edge.source_id, edge.target_id}
        }),
        "intelligent_top_5": [node.label for node in expanded.nodes],
        "example_expansion_response": expanded.model_dump(mode="json"),
        "example_evidence_response": ExpansionService(store).evidence(
            "evaluation", expanded.edges[0].id,
        ) if expanded.edges else None,
        "limitations": "Small synthetic regression sample; needs independently labeled real documentation and recall evaluation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate_sample(args.sample)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
