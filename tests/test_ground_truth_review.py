from collections import Counter

import pytest

from evaluation.real_world.compare_coverage import COVERAGE, ROOT, load_labels, read_review
from evaluation.real_world.prepare_ground_truth_review import (
    CHECKLIST_FIELDS, OMISSION_CHECKS, RELATIONSHIP_FIELDS, REVIEW_DIR, finalize, prepare_rows,
    read_csv,
)
from knowledge.extraction_batch import _read_chunks


@pytest.fixture
def review_package():
    chunks, errors = _read_chunks(ROOT / "chunking_results/chunks.jsonl")
    assert not errors
    selected = {chunk.chunk_id: (line, chunk) for line, chunk in chunks if line in OMISSION_CHECKS}
    labels = load_labels(COVERAGE / "ground_truth_draft.jsonl", selected)
    decisions = read_review(COVERAGE / "ground_truth_review.csv", labels)
    return selected, *prepare_rows(selected, labels, decisions)


def test_review_csv_preserves_multiline_source_and_pending_labels(review_package):
    chunks, relationships, checklist = review_package
    assert read_csv(REVIEW_DIR / "relationship_review.csv", RELATIONSHIP_FIELDS) == relationships
    assert read_csv(REVIEW_DIR / "chunk_checklist.csv", CHECKLIST_FIELDS) == checklist
    assert len(checklist) == len(chunks) == 20
    assert Counter(row["proposed_label"] for row in relationships) == {
        "explicit": 41, "taxonomy_gap": 9, "ambiguous": 5, "unsupported": 5,
    }
    assert {row["review_status"] for row in relationships} == {"pending_review"}


def test_finalize_requires_human_decisions_and_verbatim_new_evidence(review_package):
    chunks, relationships, checklist = review_package
    with pytest.raises(ValueError, match="Complete the omission checklist"):
        finalize(chunks, relationships, checklist, relationships, checklist)

    inventories = [dict(row, inventory_status="reviewed", reviewer="Test Reviewer")
                   for row in checklist]
    decisions = [dict(row, review_status={
        "explicit": "approved", "taxonomy_gap": "needs_taxonomy_change",
        "ambiguous": "ambiguous", "unsupported": "rejected",
    }[row["proposed_label"]]) for row in relationships]
    unsupported = next(row for row in decisions if row["proposed_label"] == "unsupported")
    unsupported["review_status"] = "approved"
    with pytest.raises(ValueError, match="cannot enter Ground Truth"):
        finalize(chunks, relationships, checklist, decisions, inventories)
    unsupported["review_status"] = "rejected"
    assert len(finalize(chunks, relationships, checklist, decisions, inventories)) == 41

    changed = next(row for row in decisions if row["annotation_id"] == "L26-R01")
    saved_hash = changed["content_hash"]
    changed["content_hash"] = "changed"
    with pytest.raises(ValueError, match="Original review fields differ"):
        finalize(chunks, relationships, checklist, decisions, inventories)
    changed["content_hash"] = saved_hash

    changed["review_status"] = "rejected"
    new = dict.fromkeys(RELATIONSHIP_FIELDS, "")
    new.update(annotation_id="H-26-01", chunk_id=changed["chunk_id"],
               source_entity=changed["source_entity"], target_entity=changed["target_entity"],
               relationship_type=changed["relationship_type"], review_status="approved",
               exact_source_evidence="paraphrase")
    with pytest.raises(ValueError, match="Exact evidence must occur"):
        finalize(chunks, relationships, checklist, [*decisions, new], inventories)
    new["exact_source_evidence"] = changed["exact_source_evidence"]
    approved = finalize(chunks, relationships, checklist, [*decisions, new], inventories)
    assert len(approved) == 41
    assert approved[-1]["annotation_id"] == "H-26-01"
    assert approved[-1]["content_hash"] == saved_hash
    assert approved[-1]["reviewer"] == "Test Reviewer"
