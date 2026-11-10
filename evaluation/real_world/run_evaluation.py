"""Evaluate available real pipeline stages without substituting missing modules.

Run: python evaluation/real_world/run_evaluation.py
Each run writes a new directory; existing datasets and graph data are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.cleaning import clean_document
from knowledge.models import GraphPolicy
from scripts.verify_cleaning import verify_document


def write_jsonl(path, records):
    with path.open('x', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')


def run(input_paths=None, output_root=None):
    started = perf_counter()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    directory = Path(output_root or ROOT / 'evaluation/real_world/runs') / run_id
    for child in ('datasets', 'outputs', 'reports'):
        (directory / child).mkdir(parents=True, exist_ok=False)
    paths = input_paths if input_paths is not None else sorted((ROOT / 'output').glob('page*.json'))
    raw, cleaned, checks, errors, duplicates = [], [], [], [], []
    seen = set()
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            from urllib.parse import urlsplit
            url = urlsplit(data['url'])
            if url.scheme != 'https' or url.netloc != 'fastapi.tiangolo.com':
                raise ValueError('not_official_fastapi_source')
            if url.query or url.username or url.password:
                raise ValueError('credential_or_query_bearing_source_not_exported')
            if data['url'] in seen:
                duplicates.append(data['url'])
                continue
            seen.add(data['url'])
            document_id = 'doc_' + hashlib.sha256(data['url'].encode()).hexdigest()
            raw.append({'document_id': document_id, **data})
        except Exception as error:
            errors.append({'stage': 'dataset', 'file': Path(path).name,
                           'error_type': type(error).__name__})
    write_jsonl(directory / 'datasets/raw_documents.jsonl', raw)
    cleaning_start = perf_counter()
    for data in raw:
        try:
            result = clean_document(data).model_dump(mode='json')
            # Existing verification checks heading hierarchy, raw code source,
            # links/images, technical terms, metadata and idempotency.
            try:
                _, inspection = verify_document(data)
                inspection['status'] = 'passed'
            except AssertionError:
                inspection = {'url': data['url'], 'status': 'failed',
                              'reason': 'existing_preservation_verifier_failed'}
            checks.append(inspection)
            result['content_hash'] = hashlib.sha256(result['markdown'].encode()).hexdigest()
            cleaned.append(result)
        except Exception as error:
            errors.append({'stage': 'cleaning', 'document_id': data['document_id'],
                           'error_type': type(error).__name__})
    cleaning_seconds = perf_counter() - cleaning_start
    write_jsonl(directory / 'datasets/cleaned_documents.jsonl', cleaned)
    write_jsonl(directory / 'outputs/cleaning_checks.jsonl', checks)
    write_jsonl(directory / 'outputs/errors.jsonl', errors)

    unavailable = {
        'chunking': 'No section-aware chunker or tokenizer integration exists; SourceChunk is only an input schema.',
        'extraction': 'StructuredExtractor requires an injected provider; no configured provider adapter exists. No requests made.',
        'normalization': 'Blocked by unavailable real chunks and extraction results.',
        'deduplication': 'Blocked by unavailable real extraction results.',
        'quality_filtering': 'Blocked by unavailable real extraction results.',
        'neo4j_import': 'No real canonical graph to import; no configured Neo4j connection. No database writes attempted.',
        'expansion': 'No resulting real graph exists; zero real node expansions executed.',
    }
    report = {
        'run_id': run_id, 'status': 'partial_blocked',
        'dataset': {'source': 'FastAPI official documentation', 'mode': 'existing_real_crawl',
                    'documents': len(raw), 'urls': [d['url'] for d in raw],
                    'target_documents': 20, 'target_met': len(raw) >= 20,
                    'duplicates_excluded': duplicates, 'chunks': None,
                    'manifest': [{'document_id': d['document_id'], 'url': d['url'],
                                  'title': d['title'], 'domain': d['metadata'].get('domain'),
                                  'crawl_time': d['metadata'].get('crawl_time'),
                                  'content_hash': hashlib.sha256(d['markdown'].encode()).hexdigest()}
                                 for d in raw]},
        'crawling': {'status': 'not_executed', 'reason': 'Reused existing suitable real crawl output; no new network requests.', 'seconds': None},
        'cleaning': {'status': 'executed', 'processed': len(raw), 'successful': len(cleaned),
                     'failed': sum(e['stage'] == 'cleaning' for e in errors),
                     'empty_documents': sum(not d['markdown'].strip() for d in cleaned),
                     'original_characters': sum(len(d['markdown']) for d in raw),
                     'cleaned_characters': sum(len(d['markdown']) for d in cleaned),
                     'preservation_checks_passed': sum(c['status'] == 'passed' for c in checks),
                     'preservation_checks_failed': sum(c['status'] == 'failed' for c in checks),
                     'seconds': cleaning_seconds},
        'stages': {name: {'status': 'not_executed', 'reason': reason, 'seconds': None}
                   for name, reason in unavailable.items()},
        'chunking': {'total_chunks': None, 'average_tokens': None, 'minimum_tokens': None,
                     'maximum_tokens': None, 'empty_chunks': None, 'failed_operations': None,
                     'chunks_per_document': None},
        'extraction': {'raw_entities': None, 'raw_relationships': None, 'failed_chunks': None,
                       'invalid_outputs': None, 'llm_request_count': 0, 'token_usage': None, 'estimated_cost': None},
        'normalization': {'canonical_entities': None, 'merged_aliases': None, 'ambiguous_merges': None},
        'relationships': {'canonical_relationships': None, 'accepted': None, 'rejected': None,
                          'rejection_reasons': None, 'evidence_validation_pass_rate': None},
        'graph': {'stored_nodes': None, 'stored_edges': None, 'idempotency_verified': None},
        'expansion': {'tested_nodes': 0, 'average_latency_ms': None, 'maximum_latency_ms': None},
        'policy': GraphPolicy().model_dump(mode='json'),
        'accuracy': {'precision': None, 'recall': None, 'precision_at_5': None,
                     'reason': 'No independently labeled real-data ground truth or real extracted graph.'},
        'errors': errors,
        'limitations': ['Only six existing unique pages are normally available; the 20-page target is not met.',
                        'This is a partial real-data functional evaluation, not an end-to-end success.',
                        'No synthetic extraction, mock provider, replacement chunker or graph was used.',
                        'Original crawl timestamps describe a saved snapshot, not a fresh documentation crawl.',
                        'Top-K relevance is unvalidated; no production accuracy benchmark is established.'],
        'total_execution_seconds': perf_counter() - started,
    }
    # Unexecuted artifacts are explicitly recorded as unavailable, not empty
    # files that could be mistaken for executed stages with zero results.
    artifacts = {name: {'status': 'not_generated', 'reason': unavailable[stage]}
                 for name, stage in {
                     'datasets/chunks.jsonl': 'chunking',
                     'outputs/extracted_entities.jsonl': 'extraction',
                     'outputs/extracted_relationships.jsonl': 'extraction',
                     'outputs/canonical_entities.jsonl': 'normalization',
                     'outputs/canonical_relationships.jsonl': 'deduplication',
                     'outputs/rejected_relationships.jsonl': 'quality_filtering',
                     'outputs/expansion_results.json': 'expansion',
                 }.items()}
    (directory / 'reports/artifact_manifest.json').write_text(json.dumps(artifacts, indent=2), encoding='utf-8')
    (directory / 'reports/pipeline_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Round 1: real-world pipeline evaluation', '', '**Status: PARTIAL / BLOCKED**', '',
             '## Dataset and cleaning', '',
             f"Real pages: {len(raw)} / target 20. Existing crawler snapshots; no new crawl.",
             f"Cleaning: {len(cleaned)} successful; {report['cleaning']['failed']} failed; "
             f"{report['cleaning']['empty_documents']} empty.",
             f"Characters: {report['cleaning']['original_characters']} -> {report['cleaning']['cleaned_characters']}.",
             f"Preservation checks passed: {report['cleaning']['preservation_checks_passed']}/{len(checks)}.", '',
             *['- ' + d['url'] for d in raw], '', '## Stage execution', '',
             '| Stage | Status / blocking reason |', '| --- | --- |',
             *[f'| {stage} | NOT EXECUTED: {reason} |' for stage, reason in unavailable.items()], '',
             '## Normalization, evidence, storage and expansion', '',
             'No real extraction results exist. Canonical counts, accepted/rejected counts, alias samples, '
             'Neo4j idempotency and graph counts are unavailable. No five real expansion examples can be produced.', '',
             '## Performance', '', f'Cleaning including preservation verification: {cleaning_seconds:.6f} seconds.',
             f"Total runner time: {report['total_execution_seconds']:.6f} seconds.",
             'Unexecuted stage times, expansion latency, LLM token usage and costs are null, not zero.', '',
             '## Observed issues and limitations', '', *['- ' + x for x in report['limitations']], '',
             'No independent real-data ground truth exists; precision and recall cannot be calculated. '
             'Evidence pass rates must not be called extraction accuracy.', '',
             '## Next steps', '',
             'Implement/configure the missing chunker and its token counting, and configure a real provider adapter '
             'for StructuredExtractor. Then rerun extraction and the existing KnowledgePipeline without tuning '
             'prompts, scores or thresholds. Configure Neo4j only when real canonical outputs are available. '
             'Expand the dataset to 20–30 official pages and independently label relevance before measuring precision.', '']
    (directory / 'reports/pipeline_report.md').write_text('\n'.join(lines), encoding='utf-8')
    # Verify every generated machine-readable artifact can be read back.
    for path in directory.rglob('*'):
        if path.suffix == '.json':
            json.loads(path.read_text(encoding='utf-8'))
        elif path.suffix == '.jsonl':
            for line in path.read_text(encoding='utf-8').splitlines():
                json.loads(line)
    return directory, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    directory, report = run(output_root=args.output_root)
    print(json.dumps({'status': report['status'], 'documents': report['dataset']['documents'],
                      'cleaning': report['cleaning'], 'reports': str(directory / 'reports')}, indent=2))
    # Distinguish a successfully generated partial report from E2E success.
    return 2 if report['status'] == 'partial_blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
