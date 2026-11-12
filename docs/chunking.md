# Section-aware chunking

`knowledge.chunking.SectionChunker` consumes a cleaned document model or mapping.
It reuses the existing Markdown parser, preserves H1–H6 hierarchy (including
Setext headings), and emits `SectionChunk` objects derived from `SourceChunk`.
Pass a `SectionChunk` directly to `StructuredExtractor.extract_async` to keep
its document title, heading path, and eligibility metadata. Use
`chunk.as_source_chunk()` for consumers that require the base `SourceChunk`.

```python
from knowledge.chunking import SectionChunker, ChunkingConfig
chunks = SectionChunker(ChunkingConfig(max_bytes=4096, overlap_bytes=256)).chunk(
    cleaned_document, project_id="fastapi-real-evaluation",
)
```

Token counting uses **UTF-8 byte tokens**, a deterministic offline tokenizer.
These are conservative budget units, not a model's BPE tokens. An attempted
`tiktoken` encoding load failed because the encoding download was unavailable;
the implementation does not silently call byte counts model-token estimates.

Root Markdown blocks are packed within each section. Large ordinary blocks are
split at available whitespace, then Unicode character boundaries if necessary.
Fenced/indented code and HTML blocks remain atomic. Oversized protected blocks
are returned intact with `oversized_reason`; content is never truncated.
Overlap repeats a complete trailing paragraph only when it fits both budgets,
stays inside its section and does not copy partial code. It is a ceiling rather
than a guaranteed amount of repetition.

Records retain document/project IDs, source URL, heading path, section title,
deep-copied crawler metadata, source character offsets, overlap prefix, count,
tokenizer identity and context warnings. IDs hash project, document, source
offsets, text and configuration. Repeating the same inputs gives identical IDs.
Document edits before a chunk may change offsets and therefore its ID.

Source heading text is not repeated into every continuation, but the full path
is always available in metadata and `SourceChunk.topic`. Separate sections may
depend on earlier explanations: `cross_section_context_not_repeated` flags that
possibility, not a confirmed semantic loss. `split_large_block` flags fragmented
large paragraphs/lists. The full original block source remains recoverable from
the source document and offsets. Markdown reference definitions in other sections
are not automatically copied; consumers can resolve them against the document.

Run on all six real crawler documents through the existing cleaner:

```powershell
python evaluation/real_world/run_chunking.py
python -m pytest -q -rs
```

Outputs: `evaluation/real_world/chunking_results/chunks.jsonl` and
`statistics.json`. The runner checks reproducibility, complete non-whitespace
source coverage and JSON readability. The statistics include per-document counts,
token distribution, oversized blocks, errors and every context-warning section.
The earlier Round-1 partial reports remain historical; this command executes
the chunking stage independently of the LLM and Neo4j.

Cleaning logic, extraction prompts, scores, thresholds, provider and frontend
implementations are not changed by this module.

## Extraction readiness review

New configuration uses `max_bytes` and `overlap_bytes`. Legacy `max_tokens`,
`overlap_tokens` and `token_count` remain compatibility aliases for byte units;
new records expose `byte_count` and reports name budgets explicitly in bytes.
The offline chunking budget uses UTF-8 bytes. The extraction runner records
model token counts from the provider when available.

All original chunks remain exported. `extraction_eligible` and
`eligibility_reasons` mark heading-only/non-substantive chunks, obvious promotions
or sponsorship sections, and oversized blocks needing a budget review.
Classification examines the source body, not repeated overlap, so copied context
cannot make an empty section look substantive. Cross-section diagnostics never
make a chunk ineligible.

`content_relevance` and `relevance_reasons` are inspectable heuristics, not quality
scores. Unknown content stays `technical_or_unknown` and remains eligible.
Sponsorship uses explicit section titles and excludes code-bearing chunks;
promotions require an event marker plus a call to action. Set
`relevance_enabled=False` to disable relevance classification, or
`exclude_obvious_nontechnical=False` to keep relevance flags without excluding
those chunks. Code and original metadata are retained in every case.

`document_title`, `heading_path`, `section_title` and `text` are available through
`extraction_context()`. `as_source_chunk()` preserves the strict existing schema
and includes the document title and heading path in `topic`. The async
extractor and batch runner honor the eligibility flag and record skip reasons.
An oversized code chunk is retained intact but requires explicit budget review
before extraction. Context/header bytes and provider prompt overhead must be
budgeted separately; the chunk byte limit applies to chunk text alone.

Executed review on all six real pages: 89 chunks, 82 eligible and 7 ineligible;
4 heading-only, 4 sponsorship, 1 promotion and 1 oversized-review reason (counts
overlap). One code block remains intact at 5,105 bytes. There are 83 diagnostic
cross-section warnings, zero errors and zero empty chunks. Full test suite:
119 passed, 1 live Neo4j test skipped. The installed pyreadline3 emits a console
cleanup warning after successful tests. Detailed per-chunk reasons are exported
in `statistics.json`, alongside the complete `chunks.jsonl` dataset.
