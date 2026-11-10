import json
from pathlib import Path

from evaluation.real_world.run_evaluation import ROOT, run


def test_real_snapshot_partial_run_reports_unknown_metrics_honestly(tmp_path):
    directory, report = run([ROOT / 'output/page0006.json'], tmp_path)
    assert report['status'] == 'partial_blocked'
    assert report['cleaning']['successful'] == 1
    assert report['cleaning']['preservation_checks_passed'] == 1
    assert report['dataset']['chunks'] is None
    assert report['extraction']['raw_relationships'] is None
    assert report['extraction']['llm_request_count'] == 0
    assert report['graph']['stored_nodes'] is None
    assert report['accuracy']['precision'] is None
    assert not (directory / 'datasets/chunks.jsonl').exists()
    saved = json.loads((directory / 'reports/pipeline_report.json').read_text(encoding='utf-8'))
    assert saved == report
    clean = json.loads((directory / 'datasets/cleaned_documents.jsonl').read_text(encoding='utf-8'))
    assert clean['document_id'].startswith('doc_') and clean['metadata']['domain'] == 'fastapi.tiangolo.com'
