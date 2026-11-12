"""Compare the saved FastAPI pilot with independently reviewed source annotations."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from knowledge.extraction_batch import _read_chunks, _report_file, _write_rows
from knowledge.models import EntityType, Model, Name, RelationType, name_key

ROOT = Path("evaluation/real_world")
COVERAGE = ROOT / "coverage"
BASELINE = ROOT / "extraction_runs/2026-11-12-gemini-3.5-flash-lite"
PENDING = "PENDING_GROUND_TRUTH_REVIEW"
REVIEW_COLUMNS = ("review_status", "reviewer", "review_notes")
RELATION_TYPES = frozenset(RelationType)


class Annotation(Model):
    annotation_id: str
    dataset_line: int
    chunk_id: str
    source_url: str
    content_hash: str
    annotation_status: Literal["pending_review"]
    notes: str


class ChunkReview(Annotation):
    kind: Literal["chunk"]


class EntityLabel(Annotation):
    kind: Literal["entity"]
    name: Name
    entity_type: EntityType
    evidence: str
    aliases: list[Name]


class RelationshipLabel(Annotation):
    kind: Literal["relationship"]
    source: Name
    relation_type: RelationType | None
    target: Name
    evidence: str
    support: Literal["explicit", "ambiguous", "unsupported", "taxonomy_gap"]
    proposed_relation: str | None = None


Label = Annotated[ChunkReview | EntityLabel | RelationshipLabel, Field(discriminator="kind")]
LABELS = TypeAdapter(list[Label])
EdgeKey = tuple[str, str, str, str]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_baseline(chunks_path: Path, run_dir: Path) -> dict:
    chunks, failures = _read_chunks(chunks_path)
    if failures:
        raise ValueError("The source chunk export contains invalid rows")
    by_id = {chunk.chunk_id: (line, chunk) for line, chunk in chunks}
    pilot = run_dir / "twenty"
    statuses = [row for row in read_rows(pilot / "chunk_status.jsonl")
                if row["status"] == "success"]
    stats = read_json(pilot / "extraction_statistics.json")
    selected = {}
    for status in statuses:
        chunk_id = status["chunk_id"]
        line, chunk = by_id[chunk_id]
        if (chunk_id in selected or
                (line, chunk.url, chunk.content_hash) != (
                    status["line"], status["source_url"], status["content_hash"],
                )):
            raise ValueError(f"Pilot provenance mismatch for {chunk_id}")
        selected[chunk_id] = (line, chunk)

    replay = read_json(run_dir / "evidence-replay/candidates.json")
    candidates = replay["candidates"]
    entities = read_rows(pilot / "extracted_entities.jsonl")
    historical_accepted = read_rows(pilot / "extracted_relationships.jsonl")
    historical_rejected = read_rows(pilot / "rejected_relationships.jsonl")
    for row in [*candidates, *entities, *historical_accepted, *historical_rejected]:
        line, chunk = selected[row["chunk_id"]]
        if (row["line"], row["source_url"]) != (line, chunk.url):
            raise ValueError(f"Artifact provenance mismatch for {chunk.chunk_id}")
        if "content_hash" in row and row["content_hash"] != chunk.content_hash:
            raise ValueError(f"Artifact source hash mismatch for {chunk.chunk_id}")

    for row in candidates:
        span = row["after"]["evidence_span"]
        chunk = selected[row["chunk_id"]][1]
        if span and (not 0 <= span["start"] < span["end"] <= len(chunk.text)
                     or span["text"] != chunk.text[span["start"]:span["end"]]):
            raise ValueError(f"Replay evidence mismatch for {chunk.chunk_id}")
        if row["after"]["accepted"] and not span:
            raise ValueError(f"Replay accepted a candidate without evidence for {chunk.chunk_id}")
        if row["after"]["evidence_text_matched"] != (span is not None):
            raise ValueError(f"Replay match and evidence span disagree for {chunk.chunk_id}")

    def saved_candidate_key(row: dict, candidate) -> tuple:
        return row["chunk_id"], json.dumps(candidate, ensure_ascii=False, sort_keys=True)

    rejected = Counter(saved_candidate_key(row, row["candidate"]) for row in historical_rejected)
    replay_rejected = Counter(saved_candidate_key(row, row["candidate"]) for row in candidates
                              if not row["before"]["accepted"])
    # Historical accepted rows contain normalized endpoints and the verified quote.
    fields = ("source", "relation_type", "target", "evidence")
    accepted = Counter((row["chunk_id"], *(row[key] for key in fields))
                       for row in historical_accepted)
    replay_accepted = Counter((row["chunk_id"], *(row["candidate"][key] for key in fields))
                              for row in candidates if row["before"]["accepted"])
    counts = Counter(row["chunk_id"] for row in candidates)
    original_match_rate = replay["before"]["matched"] / len(candidates) if candidates else None
    if (len(selected) != stats["processed_chunks"] or len(selected) != stats["successful_chunks"]
            or stats["failed_chunks"] or replay["gemini_calls"] != 0
            or len(candidates) != stats["raw_relationships"]
            or len(historical_accepted) != stats["accepted_relationships"]
            or len(historical_rejected) != stats["rejected_relationships"]
            or rejected != replay_rejected or accepted != replay_accepted
            or original_match_rate != stats["evidence_match_rate"]
            or any(counts[row["chunk_id"]] != row["raw_relationships"] for row in statuses)
            or sum(row["raw_entities"] for row in statuses) != stats["raw_entities"]):
        raise ValueError("The saved pilot and replay disagree")

    for phase in ("before", "after"):
        n = sum(row[phase]["accepted"] for row in candidates)
        if replay[phase] != {
            "candidates": len(candidates), "accepted": n, "rejected": len(candidates) - n,
            "matched": sum(row[phase]["evidence_text_matched"] for row in candidates),
        }:
            raise ValueError(f"Replay totals disagree with {phase} decisions")
    return {
        "chunks": selected, "statuses": statuses, "stats": stats, "candidates": candidates,
        "entities": entities, "before": replay["before"], "after": replay["after"],
    }


def load_labels(path: Path, chunks: dict) -> list[Label]:
    labels = LABELS.validate_python(read_rows(path))
    ids = set()
    reviews = Counter()
    for label in labels:
        if label.annotation_id in ids or label.chunk_id not in chunks:
            raise ValueError(f"Duplicate annotation ID or unknown chunk for {label.annotation_id}")
        ids.add(label.annotation_id)
        line, chunk = chunks[label.chunk_id]
        if (label.dataset_line, label.source_url, label.content_hash) != (
            line, chunk.url, chunk.content_hash,
        ):
            raise ValueError(f"Annotation provenance mismatch for {label.annotation_id}")
        if isinstance(label, ChunkReview):
            reviews[label.chunk_id] += 1
            continue
        if not label.evidence.strip() or label.evidence not in chunk.text:
            raise ValueError(f"Evidence is absent from the source for {label.annotation_id}")
        if isinstance(label, RelationshipLabel):
            gap = label.support == "taxonomy_gap"
            if gap != (label.relation_type is None) or gap != bool(label.proposed_relation):
                raise ValueError(f"Invalid relation type or taxonomy proposal for {label.annotation_id}")
    if reviews != Counter(chunks.keys()):
        raise ValueError("Each original pilot chunk must have exactly one chunk review row")
    return labels


def review_row(label: Label) -> dict[str, str]:
    fields = {
        key: str(value) if value is not None else ""
        for key, value in label.model_dump(mode="json", exclude={"aliases"}).items()
    }
    if isinstance(label, EntityLabel):
        fields["aliases"] = " | ".join(label.aliases)
    return fields


REVIEW_FIELDS = (
    "annotation_id", "kind", *REVIEW_COLUMNS, "dataset_line", "name", "entity_type", "aliases",
    "source", "relation_type", "target", "support", "proposed_relation", "evidence", "notes",
    "chunk_id", "source_url", "content_hash", "annotation_status",
)


def read_review(path: Path, labels: list[Label]) -> dict[str, dict]:
    expected = {label.annotation_id: review_row(label) for label in labels}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (len(reader.fieldnames or []) != len(REVIEW_FIELDS)
                or set(reader.fieldnames or []) != set(REVIEW_FIELDS)):
            raise ValueError("The review CSV columns differ from the generated sheet")
        rows = {}
        for row in reader:
            identifier = row["annotation_id"]
            reference = expected.get(identifier)
            if (None in row or None in row.values() or reference is None or identifier in rows or any(
                row[key].replace("\r\n", "\n") != reference.get(key, "") for key in REVIEW_FIELDS
                if key not in REVIEW_COLUMNS
            )):
                raise ValueError(f"Review row differs from the draft for {identifier}")
            status = row["review_status"]
            if status not in {"pending_review", "approved", "excluded"}:
                raise ValueError(f"Invalid review status for {identifier}")
            if row["kind"] == "chunk" and (
                status == "excluded" or (status == "approved" and not row["reviewer"].strip())
            ):
                raise ValueError(f"Chunk review requires a named approver for {identifier}")
            rows[identifier] = {key: row[key] for key in REVIEW_COLUMNS}
    if rows.keys() != expected.keys():
        raise ValueError("The review CSV must contain every draft row")
    return rows


def write_review(path: Path, labels: list[Label]) -> None:
    if path.exists():
        read_review(path, labels)
        return
    with _report_file(path) as stream:
        stream.write("\ufeff")
        writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for label in labels:
            writer.writerow({**review_row(label), "review_status": "pending_review"})


def aliases_by_chunk(labels: list[EntityLabel]) -> dict[str, dict[str, str]]:
    aliases: dict[str, dict[str, str]] = defaultdict(dict)
    for label in labels:
        canonical = name_key(label.name)
        names = aliases[label.chunk_id]
        for spelling in (label.name, *label.aliases):
            key = name_key(spelling)
            if names.setdefault(key, canonical) != canonical:
                raise ValueError(f"Conflicting alias {spelling!r} in {label.chunk_id}")
    return aliases


def edge_key(chunk_id: str, row, aliases: dict) -> EdgeKey | None:
    if not isinstance(row, dict):
        return None
    source, relation, target = (row.get(key) for key in ("source", "relation_type", "target"))
    if (not isinstance(source, str) or not isinstance(target, str) or not source.strip()
            or not target.strip() or not isinstance(relation, str) or relation not in RELATION_TYPES):
        return None
    names = aliases.get(chunk_id, {})
    left, right = name_key(source), name_key(target)
    return chunk_id, names.get(left, left), relation, names.get(right, right)


def scores(tp: int, fp: int, fn: int) -> dict:
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
    }


def compare_stage(groups: dict, gold: dict, unkeyable: list[int]) -> dict:
    tp, fp, fn = groups.keys() & gold.keys(), groups.keys() - gold.keys(), gold.keys() - groups.keys()
    return {
        **scores(len(tp), len(fp) + len(unkeyable), len(fn)),
        "matches": [
            {"classification": classification, "key": key,
             "candidate_ids": groups.get(key, []), "annotation_ids": gold.get(key, [])}
            for classification, keys in (("TP", tp), ("FP", fp), ("FN", fn))
            for key in sorted(keys)
        ] + [
            {"classification": "FP", "key": None, "candidate_ids": [index], "annotation_ids": []}
            for index in unkeyable
        ],
    }


def evaluate(baseline: dict, labels: list[Label], review: dict[str, dict]) -> tuple[dict, list[dict]]:
    approved = all(
        review.get(label.annotation_id, {}).get("review_status")
        in ({"approved"} if isinstance(label, ChunkReview) else {"approved", "excluded"})
        for label in labels
    )
    included = [label for label in labels
                if review.get(label.annotation_id, {}).get("review_status") != "excluded"]
    entities = [label for label in included if isinstance(label, EntityLabel)]
    # Pending alias decisions may aid inspection. Scored matches use only approved rows.
    aliases = aliases_by_chunk(entities)
    relationships = [label for label in included if isinstance(label, RelationshipLabel)]
    indexed_labels = defaultdict(list)
    for label in relationships:
        key = edge_key(label.chunk_id, label.model_dump(mode="json"), aliases)
        if key is not None:
            indexed_labels[key].append(label)

    raw, accepted, unkeyable = defaultdict(list), defaultdict(list), []
    candidates = []
    for index, row in enumerate(baseline["candidates"], 1):
        key = edge_key(row["chunk_id"], row["candidate"], aliases)
        if key is None:
            unkeyable.append(index)
        else:
            raw[key].append(index)
            if row["after"]["accepted"]:
                accepted[key].append(index)
        candidates.append({
            "candidate_id": index, **row, "canonical_key": key,
            "content_hash": baseline["chunks"][row["chunk_id"]][1].content_hash,
            "source_annotations": [
                {"annotation_id": label.annotation_id, "support": label.support,
                 "evidence": label.evidence, "notes": label.notes,
                 "annotation_status": review.get(label.annotation_id, {}).get(
                     "review_status", label.annotation_status,
                 )}
                for label in indexed_labels[key]
            ],
        })
    positive = {key: [label.annotation_id for label in group if label.support == "explicit"]
                for key, group in indexed_labels.items()}
    gold = {key: ids for key, ids in positive.items() if ids}
    missing = []
    for label in relationships:
        if label.support not in {"explicit", "taxonomy_gap"}:
            continue
        key = edge_key(label.chunk_id, label.model_dump(mode="json"), aliases)
        if key in accepted:
            continue
        raw_ids = raw.get(key, [])
        if label.support == "taxonomy_gap":
            cause = "taxonomy_gap"
        elif raw_ids and all(not candidates[index - 1]["after"]["schema_valid"] for index in raw_ids):
            cause = "schema_violation"
        elif raw_ids:
            cause = "validator_rejected_candidate"
        else:
            cause = "not_extracted"
        missing.append({
            **label.model_dump(mode="json"),
            "annotation_status": review.get(label.annotation_id, {}).get(
                "review_status", label.annotation_status,
            ),
            "raw_candidate_ids": raw_ids, "post_validation_candidate_ids": [],
            "cause": cause, "cause_status": "reviewed" if approved else "pending_review",
        })

    entity_metrics = None
    if approved and entities:
        labeled_chunks = {label.chunk_id for label in entities}
        expected = {(label.chunk_id, name_key(label.name)) for label in entities}
        predicted = {
            (row["chunk_id"], aliases[row["chunk_id"]].get(name_key(row["name"]), name_key(row["name"])))
            for row in baseline["entities"] if row["chunk_id"] in labeled_chunks
        }
        entity_metrics = {
            "chunks_with_labels": len(labeled_chunks),
            **scores(len(expected & predicted), len(predicted - expected), len(expected - predicted)),
        }
    report = {
        "status": "GROUND_TRUTH_REVIEWED" if approved else PENDING,
        "gemini_calls": 0,
        "chunks_evaluated": len(baseline["chunks"]),
        "chunks_with_draft_or_approved_relationships": len({
            label.chunk_id for label in relationships if label.support in {"explicit", "taxonomy_gap"}
        }),
        "chunks_with_draft_or_approved_in_taxonomy_relationships": len({key[0] for key in gold}),
        "annotations_by_support": dict(sorted(Counter(label.support for label in relationships).items())),
        "in_taxonomy_relationship_keys": len(gold),
        "approved_ground_truth_relationships": len(gold) if approved else None,
        "entity_label_rows": len(entities),
        "raw_entity_rows": baseline["stats"]["raw_entities"],
        "retained_entity_rows": len(baseline["entities"]),
        "raw_entity_metrics": None,
        "original_validation": baseline["before"],
        "post_validation": baseline["after"],
        "raw_relationship_metrics": compare_stage(raw, gold, unkeyable) if approved else None,
        "post_validation_relationship_metrics": compare_stage(accepted, gold, []) if approved else None,
        "retained_entity_metrics": entity_metrics,
        "missing_by_cause": dict(sorted(Counter(row["cause"] for row in missing).items())),
        "review_decisions": review,
        "chunk_status": baseline["statuses"],
        "candidates": candidates,
        "retained_entities": baseline["entities"],
    }
    return report, missing


def coverage_markdown(report: dict, output: Path) -> str:
    status = report["status"]
    support = report["annotations_by_support"]

    def link(path: Path) -> str:
        if path.resolve().anchor == output.resolve().anchor:
            return Path(os.path.relpath(path, output)).as_posix()
        return path.resolve().as_uri()

    guide = link(ROOT / "README.md")
    analysis = link(COVERAGE / "error_analysis.md")
    lines = [
        "# FastAPI extraction coverage", "",
        f"`{status}`", "",
        "The baseline uses the same saved pilot chunks and Gemini outputs. Provider calls for this "
        f"evaluation total {report['gemini_calls']}. Post-validation means the saved Markdown-aware replay.", "",
        "| Measure | Count |", "| --- | ---: |",
        f"| Chunks evaluated | {report['chunks_evaluated']} |",
        "| Chunks with explicit or out-of-taxonomy annotations | "
        f"{report['chunks_with_draft_or_approved_relationships']} |",
        "| Chunks with explicit in-taxonomy annotations | "
        f"{report['chunks_with_draft_or_approved_in_taxonomy_relationships']} |",
        f"| Explicit in-taxonomy relationship keys | {report['in_taxonomy_relationship_keys']} |",
        f"| Explicit out-of-taxonomy relationship annotations | {support.get('taxonomy_gap', 0)} |",
        f"| Ambiguous relationship annotations | {support.get('ambiguous', 0)} |",
        f"| Unsupported relationship annotations | {support.get('unsupported', 0)} |",
        f"| Entity annotations | {report['entity_label_rows']} |",
        f"| Gemini raw relationship candidates | {report['post_validation']['candidates']} |",
        f"| Accepted in the original live run | {report['original_validation']['accepted']} |",
        f"| Accepted in the Markdown-aware replay | {report['post_validation']['accepted']} |",
        f"| Evidence matches in the replay | {report['post_validation']['matched']} |",
        f"| Gemini raw entity rows | {report['raw_entity_rows']} |",
        f"| Retained entity rows from the live run | {report['retained_entity_rows']} |", "",
    ]
    if status == PENDING:
        lines.extend([
            "Ground Truth counts, TP, FP, FN, precision, recall and F1 are pending independent "
            "review of the labels and all chunk inventories. The counts above include draft labels.", "",
        ])
    else:
        lines.extend([
            f"Approved Ground Truth contains {report['approved_ground_truth_relationships']} "
            "unique directed, in-taxonomy relationship keys.", "",
            "| Stage | TP | FP | FN | Precision | Recall | F1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for title, field in (
            ("Raw relationships", "raw_relationship_metrics"),
            ("Post-validation relationships", "post_validation_relationship_metrics"),
            ("Retained entities", "retained_entity_metrics"),
        ):
            metrics = report[field]
            if metrics is None:
                continue
            values = [str(metrics[key]) for key in ("true_positives", "false_positives", "false_negatives")]
            values += [f"{metrics[key]:.2%}" if metrics[key] is not None else "—"
                       for key in ("precision", "recall", "f1")]
            lines.append(f"| {title} | {' | '.join(values)} |")
        lines.append("")
    lines.extend([
        "## Missing relationship audit", "",
        "| Cause | Annotations |", "| --- | ---: |",
        *(f"| `{cause}` | {count} |" for cause, count in report["missing_by_cause"].items()),
        "",
        "The saved artifacts preserve raw entity counts and retained entity objects. Raw entity "
        "precision and recall are unavailable. Retained entity scores use canonical names in "
        "chunks with approved entity labels.", "",
        f"See the [review guide]({guide}#extraction-coverage), "
        f"[baseline source analysis]({analysis}), [candidate audit](extraction_comparison.json), "
        "and [missing relationship records](missing_relationships.jsonl).", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=ROOT / "chunking_results/chunks.jsonl")
    parser.add_argument("--run-dir", type=Path, default=BASELINE)
    parser.add_argument("--annotations", type=Path, default=COVERAGE / "ground_truth_draft.jsonl")
    parser.add_argument("--review", type=Path, help="Explicitly apply a completed human-review CSV")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or (COVERAGE / "reviewed" if args.review else COVERAGE)
    baseline = load_baseline(args.chunks, args.run_dir)
    labels = load_labels(args.annotations, baseline["chunks"])
    review = read_review(args.review, labels) if args.review else {}
    report, missing = evaluate(baseline, labels, review)
    output.mkdir(parents=True, exist_ok=True)
    if not args.review:
        write_review(output / "ground_truth_review.csv", labels)
    with _report_file(output / "extraction_comparison.json") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    _write_rows(output / "missing_relationships.jsonl", missing)
    with _report_file(output / "coverage_report.md") as stream:
        stream.write(coverage_markdown(report, output))
    print(report["status"])


if __name__ == "__main__":
    main()
