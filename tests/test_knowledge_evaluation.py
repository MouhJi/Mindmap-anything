from knowledge.evaluation import evaluate_sample


def test_labeled_synthetic_evaluation_is_reproducible():
    report = evaluate_sample()
    assert report == evaluate_sample()
    assert report["sample_relationships"] == 17
    assert report["duplicate_entity_rate"] == 0
    assert report["incorrect_entity_merges"] == 0
    assert report["duplicate_relationship_rate"] == 0
    assert report["accepted_relationship_precision"] == 1
    assert report["expansion_precision_at_5"] == 1
    assert report["label_agreement"] == 1
    assert "Uvicorn" in report["unfiltered_neighbors"]
    assert "Uvicorn" not in report["intelligent_top_5"]
