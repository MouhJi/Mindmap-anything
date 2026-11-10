"""Clean and chunk the six real saved FastAPI pages; export measured statistics."""
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from crawler.cleaning import clean_document
from knowledge.chunking import SectionChunker


def main():
    output = ROOT / 'evaluation/real_world/chunking_results'
    output.mkdir(parents=True, exist_ok=True)
    chunker = SectionChunker()
    chunks, documents, errors = [], [], []
    for path in sorted((ROOT / 'output').glob('page*.json')):
        try:
            document = clean_document(json.loads(path.read_text(encoding='utf-8')))
            generated = chunker.chunk(document, project_id='fastapi-real-evaluation')
            assert generated == chunker.chunk(document, project_id='fastapi-real-evaluation')
            # Check all source content survives; ignore only whitespace outside chunks.
            spans = ''.join(document.markdown[c.start_char:c.end_char] for c in generated)
            assert ''.join(spans.split()) == ''.join(document.markdown.split())
            chunks.extend(generated)
            documents.append({'url': document.url, 'chunks': len(generated)})
        except Exception as error:
            errors.append({'file': path.name, 'type': type(error).__name__, 'message': str(error)})
    with (output / 'chunks.jsonl').open('w', encoding='utf-8') as stream:
        for chunk in chunks:
            stream.write(chunk.model_dump_json() + '\n')
    counts = sorted(c.token_count for c in chunks)
    report = {'documents': documents, 'total_chunks': len(chunks), 'tokenizer': 'utf8-byte-v1',
              'token_units': 'UTF-8 bytes, not model-specific BPE tokens',
              'max_bytes': chunker.config.max_bytes, 'overlap_bytes': chunker.config.overlap_bytes,
              'eligible_for_extraction': sum(c.extraction_eligible for c in chunks),
              'ineligible_for_extraction': sum(not c.extraction_eligible for c in chunks),
              'eligibility_reason_counts': dict(Counter(reason for c in chunks for reason in c.eligibility_reasons)),
              'relevance_counts': dict(Counter(c.content_relevance for c in chunks)),
              'flagged_chunks': [{'chunk_id': c.chunk_id, 'url': c.url, 'section': c.section_title,
                                  'eligible': c.extraction_eligible, 'reasons': c.eligibility_reasons,
                                  'relevance': c.content_relevance, 'relevance_reasons': c.relevance_reasons}
                                 for c in chunks if c.eligibility_reasons or c.relevance_reasons],
              'minimum': min(counts) if counts else None, 'maximum': max(counts) if counts else None,
              'mean': mean(counts) if counts else None, 'median': median(counts) if counts else None,
              'distribution': dict(Counter('<=1024' if n <= 1024 else '<=2048' if n <= 2048 else '<=4096' if n <= 4096 else '>4096' for n in counts)),
              'oversized_chunks': [{'chunk_id': c.chunk_id, 'url': c.url, 'section': c.section_title,
                                    'bytes': c.byte_count, 'reason': c.oversized_reason}
                                   for c in chunks if c.oversized_reason],
              'context_warnings': [{'chunk_id': c.chunk_id, 'url': c.url, 'section': c.section_title,
                                    'warnings': c.context_warnings} for c in chunks if c.context_warnings],
              'empty_chunks': sum(not c.text.strip() for c in chunks), 'errors': errors}
    (output / 'statistics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for line in (output / 'chunks.jsonl').read_text(encoding='utf-8').splitlines():
        json.loads(line)
    print(json.dumps({k: v for k, v in report.items() if k not in {'context_warnings', 'oversized_chunks', 'flagged_chunks'}}, indent=2))
    print('oversized:', len(report['oversized_chunks']), 'context warnings:', len(report['context_warnings']))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
