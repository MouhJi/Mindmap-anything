# FastAPI extraction coverage error analysis

`PENDING_GROUND_TRUTH_REVIEW`

## Extraction path and saved evidence

The crawler and Markdown cleaner supplied six documentation snapshots.
Section-aware chunking produced the checked-in 89-row export. The twenty-chunk
pilot selected eligible chunks by ID. The extraction batch sent source text
and section metadata to the Gemini adapter with `technical-extraction-v2`
and the structured `extraction-result-v2` schema. The prompt required
affirmative relationships and complete verbatim prose evidence. The adapter
validated the response envelope. Local validation checked each row, retained
source-mentioned entities, and required resolved endpoints, source evidence,
and deterministic predicate support for relationships. The production
ingestion path can normalize entities, apply graph quality checks, and persist
accepted graph data. The extraction pilot stopped at file exports.

The live pilot accepted one candidate. The frozen `markdown-evidence-v2`
replay used the same eight candidates and accepted two. Its evidence spans
matched all eight quotes. The cache preserves the candidate objects and
retained entities. The original unfiltered entity array is unavailable.
The comparison links original chunk IDs, dataset lines, URLs, content hashes,
candidate payloads, both validator decisions, and recovered evidence spans.
[Chunk export](../chunking_results/chunks.jsonl) ·
[Candidate audit](extraction_comparison.json)

## Review of the eight candidates

| Candidate IDs | Source reading | Saved replay result |
| --- | --- | --- |
| 1 | The overview grounds `BASED_ON Python type hints`. It describes Python as the language used to build APIs. | Rejected |
| 2–3 | The overview credits Starlette and Pydantic for performance. The dependency relationship is explicit in the separate Dependencies chunk on dataset line 26. The overview labels are ambiguous at chunk scope. | Rejected |
| 4–5 | The standards bullet says both “Based on” and “fully compatible with” for OpenAPI and JSON Schema. The existing `BASED_ON` labels capture the first claim. Compatibility is an additional taxonomy gap. | Both evidence spans matched. The directed predicate check rejected both. |
| 6–7 | The Dependencies chunk explicitly states both dependencies in one sentence. | Both accepted. Starlette was rejected in the original live run. |
| 8 | The Python version tab labels an example. The cited text supplies no evidence that FastAPI implements Python. | Rejected |

All eight saved candidates passed row schema validation. The two
`BASED_ON` candidates for standards passed quote matching and failed the
predicate check. The parser expects a subject and verb with recognizable
endpoint groups. The source uses a subject inherited from the feature list,
a parenthetical second predicate, and a coordinated list introduced by a
colon. The validator's rejection is observed. Whether to support that
construction is a policy decision after the labels are reviewed. The two
line 26 dependencies show that the same taxonomy and validator can represent
and accept coordinated dependencies in a complete declarative sentence.

## Missing relationship causes

| Cause | Baseline observation |
| --- | --- |
| Candidate absent | 37 explicit in-taxonomy draft rows lack a matching raw candidate. Strong review examples are Swagger UI and ReDoc using named static assets (L50-R01–R03), Python supporting asynchronous code (L71-R01), and FastAPI using OpenAPI to document the API (L21-R01). |
| Taxonomy gap | Nine draft rows describe more specific compatibility, configuration, return-value, or runtime execution facts. See the proposals below. |
| Validator rejection | L02-R06 and L02-R08 have a matching raw candidate and a recovered source span. Both were rejected by the directed predicate check. |
| Insufficient local context | The request-body prose leaves the owning framework implicit (L18-R01), the server log documents one run (L65-R01), and the Dependencies section opens with a back-reference (L87-R02). These are recorded as ambiguous. |
| Source does not establish the claim | The Python implementation claim on line 40, the broad Python foundation claim on line 2, and the required async syntax claim on line 13 have unsupported labels. The last example illustrates a source-review boundary and was never predicted. |
| Schema violation | The saved artifacts contain no malformed relationship rows or failed selected chunks. |

The audit records the absence of a matching key. The reason Gemini omitted
an edge remains uncertain. The prompt's complete-sentence instruction may
discourage edges whose subjects occur in a preceding sentence, heading, list
lead-in, or signature. That may affect the recap and API references. The
absence of candidates for the direct asset statements on line 50 suggests
that context restrictions alone are insufficient to explain the pattern.
Review whether those assets are useful graph nodes before considering prompt
changes. [Missing relationship records](missing_relationships.jsonl)

## Taxonomy proposals

| Proposed type | Definition and supported examples | Counterexample |
| --- | --- | --- |
| `COMPATIBLE_WITH` | A product explicitly states compatibility with a named standard or interface. FastAPI is described as fully compatible with OpenAPI and JSON Schema (L02-R07, L02-R09). Use the product as source and the standard as target. | Using OpenAPI to document an API (L21-R01) alone establishes usage. A compatibility statement by itself gives no evidence of formal certification. |
| `MUTUALLY_EXCLUSIVE_WITH` | Two settings cannot be used together in the same declared scope. The `license_info.identifier` and `license_info.url` fields are mutually exclusive (L33-R03). | An example that chooses one of two settings establishes a choice in that example. |
| `DEFAULT_ENDPOINT` | A resource or interface is normally served at a documented path. The OpenAPI schema defaults to `/openapi.json` and Swagger UI docs normally use `/docs` (L40-R03, L58-R03). | `/api/v1/openapi.json` appears as an explicitly configured example. |
| `RETURNS` | Calling a function yields a documented result or result type. An `async def` function returns a coroutine (L83-R01). | The analogy between Python coroutines and Go goroutines describes similarity. |
| `RUNS_IN` | A callable or workload is executed in a named runtime context under the documented condition. A synchronous path operation function and a synchronous dependency run in the external thread pool (L86-R02, L87-R01). | The documentation's plain-`def` rule supplies no equivalent thread-pool claim for an `async def` callable. |

`COMPATIBLE_WITH` has two explicit instances in the same overview bullet.
Revisit each proposal against a wider labeled sample before adding it. Each
addition would affect the shared relation enum, provider schema and prompt,
evidence predicate and scoring rules, and any graph consumers that display
the new type. For symmetric mutual exclusion, agree on one canonical ordering
so evaluation and persistence use a single logical edge. Preserve version and
default qualifiers when reviewing configuration and runtime relations.

## Follow-up after independent review

1. Prioritize approved omissions from complete affirmative prose. If those
   omissions persist, trial a versioned prompt example for already-supported
   relations such as `USES`. Evaluate quote fidelity and precision alongside
   recall.
2. If review confirms a need to support structured prose, use small offline
   regressions for the standards bullet, list lead-ins, and API reference
   descriptions. Include counterexamples for version tabs, hypothetical
   examples and nearby mentions. Resolve the desired evidence policy before
   changing the validator.
3. If a live comparison is authorized later, freeze the original baseline and
   rerun the same 20 chunks with versioned prompts and recorded API usage and
   latency. Use the approved labels. Reserve independently labeled chunks for
   held-out evaluation if the original 20 informed tuning.
