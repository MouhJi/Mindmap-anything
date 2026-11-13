"""Prepare or finalize the relationship review for the saved FastAPI pilot."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from knowledge.extraction_batch import _report_file, _write_rows
from knowledge.models import ExtractedRelationship, name_key

from .compare_coverage import (
    BASELINE, COVERAGE, ROOT, RelationshipLabel, load_baseline, load_labels, read_review,
)

REVIEW_DIR = COVERAGE / "human_review"
RELATIONSHIP_FIELDS = (
    "annotation_id", "dataset_line", "source_entity", "relationship_type", "target_entity",
    "proposed_label", "review_status", "reviewer_notes", "exact_source_evidence",
    "document_title", "heading_path", "source_url", "original_source_context",
    "proposed_relationship_type", "draft_notes", "annotation_status", "chunk_id", "content_hash",
)
CHECKLIST_FIELDS = (
    "dataset_line", "document_title", "heading_path", "omission_check", "explicit_drafts",
    "taxonomy_gap_drafts", "ambiguous_drafts", "unsupported_drafts", "inventory_status",
    "reviewer", "reviewer_notes", "original_source_context", "chunk_id", "source_url",
    "content_hash",
)
DECISIONS = {"approved", "rejected", "ambiguous", "needs_taxonomy_change"}
OMISSION_CHECKS = {
    2: "Review the type-hints basis, coordinated standards claims, and what the performance "
       "attribution establishes. Check each standard separately.",
    13: "Compare the synchronous and asynchronous examples. Look for explicitly described API "
        "behavior and distinguish examples from framework requirements.",
    18: "Check what the prose establishes about request bodies and Pydantic. Distinguish the "
        "documented capability from details of the sample model and route.",
    21: "Scan both feature lists and their lead-ins for omitted documentation, conversion, "
        "validation, and integration relationships. Resolve the subject of each list.",
    26: "Verify each coordinated dependency separately. Check the direction of each dependency.",
    33: "Read the metadata table for field ownership, requirements, rendering, and version "
        "constraints. Preserve the scope of nested license fields.",
    34: "Check what the minimum versions establish about license identifiers and whether the "
        "example supports anything beyond the stated configuration capability.",
    37: "Check both path operations and APIRouter for the tags capability. Distinguish "
        "documented assignment behavior from names used in the example.",
    40: "Check the schema's default route, what openapi_url controls, and which documentation "
        "interfaces depend on the schema. Preserve the disabling condition.",
    43: "Check whether the alternative CDN and asset discussion establishes any actual "
        "relationship. Retain the hypothetical scope of the example.",
    45: "Check the documented HTML helpers, asset URL parameters, schema use, and OAuth2 "
        "redirect role. Keep claims scoped to the specified configuration.",
    50: "Check each JavaScript and CSS asset against the UI named by its list lead-in. "
        "Distinguish asset usage from a default hosting claim.",
    58: "Review the signature, return description, and parameter table for omitted "
        "Swagger UI relationships. Distinguish defaults from configuration options.",
    60: "Review the return description and parameter table for omitted ReDoc relationships, "
        "including schema use, asset URLs, and optional fonts.",
    65: "Check what the prose establishes about uv run and fastapi dev. Treat the displayed "
        "Uvicorn and server paths as observations from the example run.",
    71: "Check separately for language support, the role of coroutines, and the async and await "
        "syntax. Preserve the version scope.",
    79: "Check what await does, where it is permitted in the documented example, and the "
        "scope of guidance for path operations using an awaitable library.",
    83: "Check the return contract and when execution can pause. The Go comparison "
        "describes an analogy, so check any proposed direction carefully.",
    86: "Check where synchronous path operations execute and when async def is recommended. "
        "Preserve the declared function type and the blocking I/O condition.",
    87: "Check the stated execution context of plain-def dependencies. Identify any claim "
        "that requires the preceding section to resolve its subject.",
}


def prepare_rows(chunks: dict, labels: list, review: dict) -> tuple[list[dict], list[dict]]:
    if {line for line, _ in chunks.values()} != OMISSION_CHECKS.keys():
        raise ValueError("The omission checklist is specific to the original twenty-chunk pilot")

    relationships = []
    counts = Counter()
    for label in labels:
        if not isinstance(label, RelationshipLabel):
            continue
        counts[label.chunk_id, label.support] += 1
        _, chunk = chunks[label.chunk_id]
        decision = review[label.annotation_id]
        relationships.append({
            "annotation_id": label.annotation_id, "dataset_line": str(label.dataset_line),
            "source_entity": label.source, "relationship_type": label.relation_type or "",
            "target_entity": label.target, "proposed_label": label.support,
            "review_status": decision["review_status"], "reviewer_notes": decision["review_notes"],
            "exact_source_evidence": label.evidence, "document_title": chunk.document_title,
            "heading_path": " > ".join(chunk.heading_path), "source_url": label.source_url,
            "original_source_context": chunk.text,
            "proposed_relationship_type": label.proposed_relation or "",
            "draft_notes": label.notes, "annotation_status": label.annotation_status,
            "chunk_id": label.chunk_id, "content_hash": label.content_hash,
        })

    checklist = []
    for label in labels:
        if label.kind != "chunk":
            continue
        line, chunk = chunks[label.chunk_id]
        decision = review[label.annotation_id]
        checklist.append({
            "dataset_line": str(line), "document_title": chunk.document_title,
            "heading_path": " > ".join(chunk.heading_path), "omission_check": OMISSION_CHECKS[line],
            **{f"{kind}_drafts": str(counts[chunk.chunk_id, kind])
               for kind in ("explicit", "taxonomy_gap", "ambiguous", "unsupported")},
            "inventory_status": decision["review_status"], "reviewer": decision["reviewer"],
            "reviewer_notes": decision["review_notes"], "original_source_context": chunk.text,
            "chunk_id": chunk.chunk_id,
            "source_url": chunk.url, "content_hash": chunk.content_hash,
        })
    return relationships, checklist


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with _report_file(path) as stream:
        stream.write("\ufeff")
        writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or sorted(reader.fieldnames) != sorted(fields):
            raise ValueError(f"Unexpected columns in {path}")
        rows = []
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f"Invalid CSV row ending on line {reader.line_num} in {path}")
            rows.append({key: value.replace("\r\n", "\n") for key, value in row.items()})
        return rows


def check_original(row: dict, original: dict, editable: set[str], identifier: str) -> None:
    if any(row[field] != original[field] for field in original.keys() - editable):
        raise ValueError(f"Original review fields differ for {identifier}")


def finalize(
    chunks: dict, relationships: list[dict], checklist: list[dict],
    reviewed_relationships: list[dict], reviewed_checklist: list[dict],
) -> list[dict]:
    original_chunks = {row["chunk_id"]: row for row in checklist}
    reviewers = {}
    for row in reviewed_checklist:
        chunk_id = row["chunk_id"]
        if chunk_id in reviewers or chunk_id not in original_chunks:
            raise ValueError(f"Unknown or duplicate checklist chunk {chunk_id}")
        check_original(row, original_chunks[chunk_id],
                       {"inventory_status", "reviewer", "reviewer_notes"}, chunk_id)
        if row["inventory_status"] != "reviewed" or not row["reviewer"].strip():
            raise ValueError(
                f"Complete the omission checklist for dataset line {row['dataset_line']}"
            )
        reviewers[chunk_id] = row["reviewer"].strip()
    if reviewers.keys() != original_chunks.keys():
        raise ValueError("The checklist must include every original pilot chunk")

    drafts = {row["annotation_id"]: row for row in relationships}
    seen, keys, approved = set(), set(), []
    for row in reviewed_relationships:
        identifier, chunk_id, decision = row["annotation_id"], row["chunk_id"], row["review_status"]
        if not identifier or identifier in seen or chunk_id not in chunks:
            raise ValueError(
                f"Invalid or duplicate annotation ID or unknown chunk for {identifier}"
            )
        seen.add(identifier)
        line, chunk = chunks[chunk_id]
        draft = drafts.get(identifier)
        if draft is not None:
            check_original(row, draft, {"review_status", "reviewer_notes"}, identifier)
        elif not identifier.startswith("H-") or len(identifier) <= 2:
            raise ValueError(f"Use a unique H- ID for a new relationship: {identifier}")
        else:
            for field, value in {
                "dataset_line": str(line), "chunk_id": chunk_id, "source_url": chunk.url,
                "content_hash": chunk.content_hash, "document_title": chunk.document_title,
                "heading_path": " > ".join(chunk.heading_path),
                "original_source_context": chunk.text,
            }.items():
                if row[field] and row[field] != value:
                    raise ValueError(f"New relationship {identifier} has inconsistent {field}")
        if decision not in DECISIONS:
            raise ValueError(f"Resolve the review status for {identifier}")
        evidence = row["exact_source_evidence"]
        if not evidence.strip() or evidence not in chunk.text:
            raise ValueError(f"Exact evidence must occur in the source chunk for {identifier}")
        if not row["source_entity"].strip() or not row["target_entity"].strip():
            raise ValueError(f"Supply both directed endpoints for {identifier}")
        if decision != "approved":
            continue
        if row["proposed_label"] in {"unsupported", "taxonomy_gap"}:
            raise ValueError(f"{identifier} cannot enter Ground Truth with its draft label")
        relation = ExtractedRelationship(
            source=row["source_entity"], target=row["target_entity"],
            relation_type=row["relationship_type"], evidence=evidence, chunk_id=chunk_id,
        )
        key = chunk_id, name_key(relation.source), relation.relation_type, name_key(relation.target)
        if key in keys:
            raise ValueError(f"Duplicate approved relationship for {identifier}")
        keys.add(key)
        approved.append({
            "annotation_id": identifier, "dataset_line": line, "chunk_id": chunk_id,
            "document_id": chunk.document_id, "source_url": chunk.url,
            "content_hash": chunk.content_hash, "source": relation.source,
            "relation_type": relation.relation_type.value, "target": relation.target,
            "evidence": relation.evidence, "annotation_status": "approved",
            "reviewer": reviewers[chunk_id], "reviewer_notes": row["reviewer_notes"],
        })
    if drafts.keys() - seen:
        raise ValueError("The relationship review must include every original draft")
    return approved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=BASELINE)
    parser.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    parser.add_argument("--finalize", action="store_true", help="Export completed human decisions")
    args = parser.parse_args()

    baseline = load_baseline(ROOT / "chunking_results/chunks.jsonl", args.run_dir)
    chunks = baseline["chunks"]
    labels = load_labels(COVERAGE / "ground_truth_draft.jsonl", chunks)
    decisions = read_review(COVERAGE / "ground_truth_review.csv", labels)
    relationships, checklist = prepare_rows(chunks, labels, decisions)
    folder = args.review_dir
    paths = folder / "relationship_review.csv", folder / "chunk_checklist.csv"
    if args.finalize:
        approved = finalize(
            chunks, relationships, checklist, read_csv(paths[0], RELATIONSHIP_FIELDS),
            read_csv(paths[1], CHECKLIST_FIELDS),
        )
        output = folder / "approved_relationships.jsonl"
        if output.exists():
            raise SystemExit(f"An approved export already exists at {output}")
        _write_rows(output, approved)
        print(f"Exported {len(approved)} approved relationships to {output}")
        return
    if any(path.exists() for path in paths):
        raise SystemExit(f"Review sheets already exist in {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(paths[0], RELATIONSHIP_FIELDS, relationships)
    write_csv(paths[1], CHECKLIST_FIELDS, checklist)
    print(f"Prepared {len(relationships)} relationships and {len(checklist)} chunk checklists")


if __name__ == "__main__":
    main()
