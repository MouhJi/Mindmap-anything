# Real-world FastAPI evaluation

## Round 1 cleaning baseline

From the repository root:

```powershell
python evaluation/real_world/run_evaluation.py
```

Each invocation creates a unique directory under `evaluation/real_world/runs/`
with snapshots, preservation checks, artifact availability manifest, JSON report
and Markdown report. Existing crawl and production graph data are not modified.
The runner deliberately returns a non-success status for a blocked pipeline even
when partial reports were generated successfully.

The current checkout has six unique saved official FastAPI documents. The runner
reuses these snapshots instead of fetching new pages. It runs the actual cleaner
and existing source-preservation verifier without changing their rules.

This baseline runs through cleaning. Unexecuted stage counts are null and
unavailable artifacts are listed in `artifact_manifest.json`. The 20-page target
remains unmet. Section chunking and Gemini extraction have separate entry
points below. Existing Round 1 reports describe their historical runs.

Neo4j's existing integration uses `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and
optionally `NEO4J_DATABASE`. No values are exported by this evaluation. Configure
these only for a future isolated evaluation import after real extraction exists.

The baseline regression exercises a saved FastAPI page and verifies partial-run
reporting, provenance, readable artifacts and null unavailable metrics.

No independently labeled ground truth was added; precision, recall and Top-K
semantic relevance are not established by this round.

## Gemini extraction

Install the optional SDK and test dependencies from the repository root.

```powershell
python -m pip install -e ".[llm,test]"
```

Set `GEMINI_API_KEY` and `GEMINI_MODEL` in the process environment. Use the API
model ID, such as `gemini-3.5-flash-lite`, and select a model your key can use
for JSON structured output. Google limits Gemini 2.5 access to existing users,
so a listed model can still return HTTP 404 for generation. Keep the key in
your local environment and use `.env.example` as a placeholder template.
[Gemini model guide](https://ai.google.dev/gemini-api/docs/models) ·
[Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

| Optional variable | Default | Effect |
| --- | --- | --- |
| `LLM_TEMPERATURE` | `0` | Sampling temperature between 0 and 2 |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout for each request attempt |
| `LLM_MAX_CONCURRENT_REQUESTS` | `2` | Concurrent requests per adapter |
| `LLM_MAX_ATTEMPTS` | `3` | Total attempts, including the initial request (1–5) |

Run the adapter smoke test first. It makes one small request using the same
response schema as extraction. The runner validates array limits locally.
Continue to the extraction pilots after the test reports `1 passed`.

```powershell
$env:GRAPH_TEST_GEMINI = '1'
python -m pytest -q -s -rs tests/test_gemini_live.py
```

The existing chunk export contains 89 chunks across six documents. To rebuild
it from the saved pages, run `python evaluation/real_world/run_chunking.py`.
The following row numbers select eligible chunks in the checked-in export.
The five-chunk pilot covers architecture dependencies, the OpenAPI URL,
`async` and `await`, coroutines, and async dependencies.

```powershell
$dataset = 'evaluation/real_world/chunking_results/chunks.jsonl'
$runRoot = 'evaluation/real_world/extraction_runs'
$chunks = @(Get-Content -Encoding UTF8 $dataset | ForEach-Object { $_ | ConvertFrom-Json })

function Invoke-FastApiExtraction {
    param([string]$Name, [int[]]$Rows)
    $selection = foreach ($row in $Rows) { '--chunk-id'; $chunks[$row - 1].chunk_id }
    python -m knowledge.extraction_batch $dataset --output-dir "$runRoot/$Name" `
        --cache "$runRoot/cache.sqlite3" @selection
}

Invoke-FastApiExtraction -Name five -Rows 26,40,79,83,87
```

Review the five-chunk report and its source quotes before spending API quota on
the twenty-chunk pilot. The larger selection adds API references, code-heavy
examples, short explanatory sections, and narrative text. The shared cache
reuses successful extractions when their inputs match.

```powershell
Invoke-FastApiExtraction -Name twenty -Rows 2,13,18,21,26,33,34,37,40,43,45,50,58,60,65,71,79,83,86,87
```

After both pilots work, run the full eligible dataset explicitly.

```powershell
python -m knowledge.extraction_batch $dataset --output-dir "$runRoot/full" `
    --cache "$runRoot/cache.sqlite3" --all
```

`--limit N` selects the first N eligible chunks. `--batch-size` controls the
number scheduled at a time and `--concurrency` limits active chunk tasks. The
adapter also applies `LLM_MAX_CONCURRENT_REQUESTS` to API calls. Use one active
runner per output directory. To resume, repeat the same command with the same
cache path. Each success is checkpointed before the batch finishes. Failures
are tried again on the next invocation. Model/settings, prompt, schema,
policy, source content and supplied context participate in cache invalidation.

### Extraction artifacts

| File | Contents |
| --- | --- |
| `chunk_status.jsonl` | Chunk provenance, success/failure/skip status, cache reuse and provider metrics |
| `extracted_entities.jsonl` | Deduplicated, source-mentioned entities and provenance |
| `extracted_relationships.jsonl` | Accepted directed edges with exact evidence and grounding outcomes |
| `rejected_relationships.jsonl` | Rejected candidates and controlled reasons, including malformed rows |
| `extraction_failures.jsonl` | Invalid input rows and per-chunk provider or extraction errors |
| `extraction_statistics.json` | Counts, evidence match rate, attempts, available token totals and elapsed time |

`eligible_chunks` covers the input dataset. `processed_chunks` counts selected
eligible chunks, including cache hits. `skipped_chunks` counts ineligible input.
The runner returns a nonzero status for invalid input rows or failed chunks
after writing the available results. Provider attempts and token totals cover
fresh calls. Per-chunk metrics on cache hits retain the original measurements.
Token totals sum reported counts, with null for unavailable counts and coverage
fields for partial usage. Provider latency includes waiting and backoff.

The evidence match rate measures exact and Markdown-aware quote matches among
relationship candidates in current exports. The original live pilot used
exact matching. Acceptance additionally requires deterministic directed predicate
support and a complete prose assertion. The English patterns can miss valid
paraphrases, coordinated targets, implicit references, and facts expressed in
code. Broader discourse context and entity type correctness still need human
review. Precision and recall require independent labels.


### Replay a saved pilot offline

Use the original chunk export, pilot status and statistics, and SQLite cache to
reevaluate saved candidates after a validator change. The replay opens the
cache read-only and checks that the baseline totals and source hashes match
the saved pilot. It writes a before-and-after report and a JSON audit with the
original candidate quotes and verified source spans.

```powershell
$run = 'evaluation/real_world/extraction_runs/2026-11-12-gemini-3.5-flash-lite'
python -m evaluation.real_world.replay_evidence --chunks evaluation/real_world/chunking_results/chunks.jsonl `
    --pilot "$run/twenty" --cache "$run/cache.sqlite3" --output-dir "$run/evidence-replay"
```

The replay uses saved candidates and makes zero provider requests.

## Extraction coverage

The [coverage baseline](coverage/coverage_report.md) compares the original 20
FastAPI chunks and saved Gemini candidates with source-derived draft annotations.
It uses the frozen Markdown-aware replay for post-validation results. The
[source analysis](coverage/error_analysis.md) documents the extraction path,
candidate errors, and proposed taxonomy additions. Run the comparison offline
from the repository root.

```powershell
python -B -m evaluation.real_world.compare_coverage
```

The command reads the checked-in chunk export and the existing local
`2026-11-12-gemini-3.5-flash-lite` directory under `extraction_runs/`. That
directory is Git-ignored. On another checkout, supply the preserved run directory
with `--run-dir`. The runner needs the saved `twenty/` status, statistics,
entity and relationship exports, plus `evidence-replay/candidates.json`. It
does not open the cache or call Gemini. The [comparison JSON](coverage/extraction_comparison.json)
also records the original candidates, both validator decisions, and source provenance.

### Review and score

1. Copy the [review CSV](coverage/ground_truth_review.csv) to
   `ground_truth_reviewed.csv`. It uses UTF-8 and includes multiline Markdown
   quotes. The `dataset_line` column identifies the one-based line in the
   [original chunk export](chunking_results/chunks.jsonl). Check the full source
   chunk before consulting the saved predictions.
2. For each entity and relationship row, set `review_status` to `approved`
   if the label, evidence, scope and support classification are correct, or
   `excluded` if the row should be omitted. Approval of an `ambiguous` or
   `unsupported` row confirms that disposition. Record comments in
   `review_notes`. For label corrections or additions, revise a copy of the
   [draft JSONL](coverage/ground_truth_draft.jsonl) and generate a fresh CSV
   with `--annotations PATH --output-dir NEW_DIRECTORY`. Review decisions
   are tied to the source hash and label contents.
3. Mark each of the 20 `chunk` rows `approved` and fill in `reviewer` after
   checking that its relationship and entity inventories are complete. This
   includes chunks with zero supported relationships. Save the sheet as a
   comma-delimited UTF-8 CSV. Edit only `review_status`, `reviewer`, and
   `review_notes` in the CSV.
4. Apply the reviewed sheet. Pass the same `--annotations PATH` if the review
   used revised labels. The default output for this command is `coverage/reviewed/`.

```powershell
python -B -m evaluation.real_world.compare_coverage --review evaluation/real_world/coverage/ground_truth_reviewed.csv
```

The command emits metrics after all 20 inventories are approved and all
label rows are resolved. Draft runs and incomplete reviews report
`PENDING_GROUND_TRUTH_REVIEW`. The default run preserves existing CSV edits
and requires an explicit `--review` path to apply them.

The relationship denominator contains approved, explicit, in-taxonomy
relationships. Matching uses the chunk ID, canonical source and target names,
and directed relation type. Aliases are scoped to each chunk. Repeated
predictions for the same key count once per stage, and each raw candidate
with an unreadable key counts as a false positive. Raw candidates with a
readable key can match even if their quote or other fields fail validation.
The candidate audit preserves those validation outcomes. Taxonomy gaps,
ambiguous claims and unsupported claims contribute no positive keys.
Entity scores use canonical names among chunks with approved entity labels.
The cache and pilot exports provide raw entity counts and retained objects,
so the report can score retained entity names only.
