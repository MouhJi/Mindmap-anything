# Round 1: real-world pipeline evaluation

**Status: PARTIAL / BLOCKED**

## Dataset and cleaning

Real pages: 1 / target 20. Existing crawler snapshots; no new crawl.
Cleaning: 1 successful; 0 failed; 0 empty.
Characters: 24491 -> 22822.
Preservation checks passed: 1/1.

- https://fastapi.tiangolo.com/async/

## Stage execution

| Stage | Status / blocking reason |
| --- | --- |
| chunking | NOT EXECUTED: No section-aware chunker or tokenizer integration exists; SourceChunk is only an input schema. |
| extraction | NOT EXECUTED: StructuredExtractor requires an injected provider; no configured provider adapter exists. No requests made. |
| normalization | NOT EXECUTED: Blocked by unavailable real chunks and extraction results. |
| deduplication | NOT EXECUTED: Blocked by unavailable real extraction results. |
| quality_filtering | NOT EXECUTED: Blocked by unavailable real extraction results. |
| neo4j_import | NOT EXECUTED: No real canonical graph to import; no configured Neo4j connection. No database writes attempted. |
| expansion | NOT EXECUTED: No resulting real graph exists; zero real node expansions executed. |

## Normalization, evidence, storage and expansion

No real extraction results exist. Canonical counts, accepted/rejected counts, alias samples, Neo4j idempotency and graph counts are unavailable. No five real expansion examples can be produced.

## Performance

Cleaning including preservation verification: 0.336799 seconds.
Total runner time: 0.368488 seconds.
Unexecuted stage times, expansion latency, LLM token usage and costs are null, not zero.

## Observed issues and limitations

- Only six existing unique pages are normally available; the 20-page target is not met.
- This is a partial real-data functional evaluation, not an end-to-end success.
- No synthetic extraction, mock provider, replacement chunker or graph was used.
- Original crawl timestamps describe a saved snapshot, not a fresh documentation crawl.
- Top-K relevance is unvalidated; no production accuracy benchmark is established.

No independent real-data ground truth exists; precision and recall cannot be calculated. Evidence pass rates must not be called extraction accuracy.

## Next steps

Implement/configure the missing chunker and its token counting, and configure a real provider adapter for StructuredExtractor. Then rerun extraction and the existing KnowledgePipeline without tuning prompts, scores or thresholds. Configure Neo4j only when real canonical outputs are available. Expand the dataset to 20–30 official pages and independently label relevance before measuring precision.
