import csv

import pytest

from evaluation.real_world.compare_coverage import (
    COVERAGE, PENDING, ROOT, evaluate, load_labels, read_review, read_rows, write_review,
)
from knowledge.extraction_batch import _read_chunks, _write_rows


def test_draft_covers_the_original_twenty_chunk_inventories():
    chunks, failures = _read_chunks(ROOT / "chunking_results/chunks.jsonl")
    assert not failures
    lines = {2, 13, 18, 21, 26, 33, 34, 37, 40, 43, 45, 50, 58, 60, 65, 71, 79, 83, 86, 87}
    selected = {chunk.chunk_id: (line, chunk) for line, chunk in chunks if line in lines}
    labels = load_labels(COVERAGE / "ground_truth_draft.jsonl", selected)
    assert {label.dataset_line for label in labels if label.kind == "chunk"} == lines
    assert {label.annotation_status for label in labels} == {"pending_review"}


def test_review_gate_and_directed_matching(tmp_path):
    chunks, failures = _read_chunks(ROOT / "chunking_results/chunks.jsonl")
    assert not failures
    selected = {chunk.chunk_id: (line, chunk) for line, chunk in chunks if line in {26, 43, 50}}

    draft = tmp_path / "draft.jsonl"
    _write_rows(draft, (row for row in read_rows(COVERAGE / "ground_truth_draft.jsonl")
                        if row["chunk_id"] in selected))
    labels = load_labels(draft, selected)
    for label in labels:
        if label.annotation_id == "L26-E01":
            label.aliases = ["Fast API"]
    chunk_id = next(key for key, (line, _) in selected.items() if line == 26)
    asset_id = next(key for key, (line, _) in selected.items() if line == 50)

    def candidate(source, target, *, chunk=chunk_id, accepted=False, schema_valid=True):
        return {
            "chunk_id": chunk,
            "candidate": {"source": source, "target": target,
                          "relation_type": "DEPENDS_ON" if chunk == chunk_id else "USES"},
            "after": {"accepted": accepted, "schema_valid": schema_valid},
        }

    baseline = {
        "chunks": selected, "stats": {"raw_entities": 2}, "statuses": [],
        "entities": [{"chunk_id": chunk_id, "name": "FastAPI"},
                     {"chunk_id": chunk_id, "name": "fastapi"}],
        "before": {}, "after": {},
        "candidates": [
            candidate("FastAPI", "Starlette", accepted=True),
            candidate(" Fast API ", "STARLETTE"),
            candidate("Pydantic", "FastAPI"),
            candidate("FastAPI", "Pydantic", schema_valid=False),
            candidate("ReDoc", "REDOC.STANDALONE.JS", chunk=asset_id),
            candidate("FastAPI", ["Pydantic"], schema_valid=False),
        ],
    }
    sheet = tmp_path / "review.csv"
    write_review(sheet, labels)
    with sheet.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)

    def save_review():
        with sheet.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return read_review(sheet, labels)

    for row in rows:
        row["review_status"] = "approved"
        row["reviewer"] = "Test reviewer"
        if row["annotation_id"] == "L43":
            row["review_status"] = "pending_review"
        if row["annotation_id"] == "L50-R02":
            row["review_status"] = "excluded"
    partial = save_review()
    report, _ = evaluate(baseline, labels, partial)
    assert report["status"] == PENDING
    assert report["approved_ground_truth_relationships"] is None
    assert report["raw_relationship_metrics"] is None
    assert report["post_validation_relationship_metrics"] is None
    assert report["retained_entity_metrics"] is None

    next(row for row in rows if row["annotation_id"] == "L43")["review_status"] = "approved"
    complete = save_review()
    report, missing = evaluate(baseline, labels, complete)
    assert report["status"] == "GROUND_TRUTH_REVIEWED"
    raw = report["raw_relationship_metrics"]
    post = report["post_validation_relationship_metrics"]
    assert (raw["true_positives"], raw["false_positives"], raw["false_negatives"]) == (3, 2, 1)
    assert (post["true_positives"], post["false_positives"], post["false_negatives"]) == (1, 0, 3)
    assert raw["f1"] == 2 / 3
    assert next(row for row in missing if row["annotation_id"] == "L26-R01")["cause"] == (
        "schema_violation"
    )
    assert report["retained_entity_metrics"]["true_positives"] == 1
    write_review(sheet, labels)
    assert read_review(sheet, labels) == complete

    rows[0]["content_hash"] = "different source"
    with pytest.raises(ValueError, match="differs from the draft"):
        save_review()
