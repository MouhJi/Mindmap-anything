# Real-world evaluation, Round 1

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

There is currently no section-aware chunker or configured completion-provider
adapter. No mock, synthetic output, replacement chunker or fabricated graph is
used. Unexecuted downstream counts are null, unavailable artifacts are listed in
`artifact_manifest.json`, and no real expansion examples are claimed. The 20-page
target remains unmet. A configured provider API key alone is insufficient without
its actual adapter and the missing chunking integration.

Neo4j's existing integration uses `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` and
optionally `NEO4J_DATABASE`. No values are exported by this evaluation. Configure
these only for a future isolated evaluation import after real extraction exists.

Executed validation: 106 tests passed and one live Neo4j integration test skipped.
The new regression exercises a real saved FastAPI page and verifies partial-run
reporting, provenance, readable artifacts and null unavailable metrics.

No independently labeled ground truth was added; precision, recall and Top-K
semantic relevance are not established by this round.
