# Knowledge quality and intelligent expansion

## Inspected architecture and scope

The starting repository contains `crawler/` (Crawl4AI rendering, extraction of
article Markdown/text, BFS traversal, deduplication and Pydantic documents) and
`crawler/cleaning/` (light cleaning), with saved real crawler pages and tests.
It has no chunker, structured LLM extraction/provider configuration, Neo4j
repository/schema, backend web framework, graph frontend, design system, or
authentication infrastructure. No Neo4j environment configuration or driver was
available during implementation.

The new independent `knowledge/` package consumes supplied `SourceChunk` objects;
it does not manufacture chunk boundaries or alter crawler/cleaning behavior.
The WSGI read adapter avoids choosing another application framework. The
extractor supports an injected synchronous completion callable or the async
structured provider contract.
No LLM calls occur during normalization, quality checking, or node expansion.

## File manifest

| New file | Responsibility |
| --- | --- |
| `knowledge/__init__.py` | Public model exports |
| `knowledge/models.py` | Schemas, enums, finite score validation, IDs and policy |
| `knowledge/extraction.py` | Provider protocol, technical extraction prompt, schema validation |
| `knowledge/provider.py` | Async structured completion, Gemini settings, retries and metrics |
| `knowledge/extraction_batch.py` | Section-chunk JSONL runner, checkpoints and audit reports |
| `knowledge/normalization.py` | Incremental scoped name/alias/context resolution |
| `knowledge/quality.py` | Evidence grounding, directed predicates, independent importance/confidence |
| `knowledge/ingestion.py` | Transactional chunk replacement, canonical edges, evidence and audit |
| `knowledge/repository.py` | Repository protocol and indexed offline reference store |
| `knowledge/neo4j.py` | Optional transactional persistence and bounded Cypher |
| `knowledge/migrations/001_quality_graph.cypher` | Scoped uniqueness constraints and evidence indexes |
| `knowledge/expansion.py` | Ranking, eligibility, cursor validation, evidence pagination |
| `knowledge/api.py` | Local WSGI read API, validation and errors |
| `knowledge/evaluation.py` | Reproducible labeled sample evaluation |
| `knowledge/evaluation/sample.json` | 17 synthetic labeled examples and expected entity groups |
| `tests/__init__.py` | Avoid collisions with third-party packages named `tests` |
| `tests/test_knowledge.py` | Domain and HTTP regression coverage |
| `tests/test_knowledge_neo4j.py` | Query/schema contracts and opt-in live Neo4j test |
| `tests/test_knowledge_evaluation.py` | Reproducible sample expectations |
| `docs/knowledge-quality.md` | This implementation and integration guide |

Modified: `README.md` (usage), `pyproject.toml` (optional Neo4j dependency,
package discovery, packaged migration and evaluation fixture). Generated:
`output/graph-quality/evaluation.json` with actual metrics, decisions, and example
expansion/evidence responses, the built wheel/build log, and refreshed generated
`universal_docs_crawler.egg-info` package metadata. Existing crawler and
document-cleaning code is unchanged.

## Data schemas

All domain models use Pydantic, forbid unknown fields, validate assignment and
revalidate model instances at ingestion. Scores are strict finite floats in
`[0, 1]`; booleans, strings, NaN, infinity and out-of-range scores are rejected.

| Model | Fields |
| --- | --- |
| `SourceChunk` | project_id, chunk_id, document_id, HTTP(S) url, text, topic, computed content_hash |
| `ExtractedEntity` | name, controlled type, description?, aliases[] |
| `ExtractedRelationship` | source, target, controlled relation_type, description?, evidence, chunk_id, importance?, confidence? |
| `ExtractionResult` | entities[], relationships[] |
| `CanonicalEntity` | project_id, entity_id, canonical_name, entity_type, aliases[], description? |
| `CanonicalRelationship` | project_id, relationship_id, source_id, target_id, relation_type, importance, confidence, evidence_count, verified |
| `Evidence` | evidence_id, project_id, relationship_id, chunk_id, document_id, url, text, content_hash, importance, confidence, policy_version |
| `Decision` | chunk_id, source, target, relation_type, accepted, reasons[], importance, confidence |
| `ExpansionResult` | center_node, nodes[], edges[], pagination{returned, has_more, next_cursor} |

Entity types: Framework, Library, Language, Concept, API, Method, Algorithm,
Protocol, Tool, Format, Service. Relation types: BASED_ON, USES, DEPENDS_ON,
SUPPORTS, IMPLEMENTS, EXTENDS, INTEGRATES_WITH, PART_OF, PROVIDES, REQUIRES,
MENTIONS, EXAMPLE_OF. Each is a fixed enum, preventing arbitrary phrase-based
relationship types.

`StructuredExtractor(provider, provider_version="model/config-version")` passes
`messages` and `ExtractionResult.model_json_schema()` to a supplied callable.
The callable returns JSON text or a mapping. SDK-specific structured-output
configuration belongs in that adapter. An invalid response raises
`ExtractionError` without logging raw source/output. Wrong chunk IDs are rejected.
Synchronous extraction uses the explicitly supplied callable.

```python
extractor = StructuredExtractor(my_completion_adapter, provider_version="my-model-v1")
report = KnowledgePipeline(repository).ingest_chunk(source_chunk, extractor=extractor)
```

For async extraction, construct `GeminiProvider` explicitly and pass each
`SectionChunk` to `extract_async`. The request uses the existing controlled
schema. Response rows are checked individually so malformed relationships can
be audited alongside valid rows.

```python
from knowledge.extraction import StructuredExtractor
from knowledge.provider import GeminiProvider, GeminiSettings

async def extract_section(section_chunk):
    async with GeminiProvider(GeminiSettings.from_env()) as provider:
        extractor = StructuredExtractor(provider, provider_version=provider.version)
        return await extractor.extract_async(section_chunk)
```

The outcome contains a graph-compatible `ExtractionResult` in `.result` and
per-candidate `relationship_checks`. Evidence must match a complete, directly
asserted top-level prose sentence through a literal quote or a verified
Markdown-aware match. The async path records the exact original span and applies
the `deterministic-v1` scoring policy. It checks entity mentions, removes duplicate
names, omits unchecked aliases and descriptions, and flags conflicting types.
Only accepted edges enter `.result`. To ingest later, pass the result and the
same chunk to `KnowledgePipeline.ingest_chunk`. See the
[evaluation guide](../evaluation/real_world/README.md#gemini-extraction) for
provider configuration and the batch runner.

## Conservative normalization

Names are normalized with Unicode NFC, case folding, and whitespace collapse.
Punctuation is retained: C, C++, C#, .NET and NET remain distinct. Entity types
and project IDs participate in resolution. There is no edit-distance or embedding
merge, no stripping of qualifiers such as Native or asyncio, and no generic
Framework suffix removal.

Resolve against an indexed registry using exact names or declared aliases within
the same entity type/project. Shared third-party aliases do not union two existing
entities. Multiple candidates stay separate or are flagged as ambiguous; ambiguous
endpoint names cannot produce a trusted relationship. Names differing only in
spacing may merge when descriptions share at least two informative terms and
their token Jaccard overlap is at least 0.7. This is a conservative lexical context
heuristic, not semantic identity verification.

For example, FastAPI, fastapi, Fast API, and FastAPI Framework can share an entity
when aliases/context support it. React/React Native and Python/Python asyncio keep
their own identities. A small generic UI/heading vocabulary is excluded. Extracted
entities must also be mentioned in the source chunk; arbitrary hallucinated
entities do not get stored just because they occur in an extraction response.

IDs use full SHA-256 over unambiguously serialized, project-scoped tuples:

```text
entity ID: project + entity type + normalized first canonical name
edge ID: project + source ID + controlled relation type + target ID
evidence ID: edge ID + chunk ID + chunk content hash + whitespace-normalized quote
```

The registry preserves the initial entity ID when an alias is learned later.
Initial batch ordering is deterministic and prefers compact names; across
independently initialized registries, a different first-observed alias can yield a
different ID. Existing IDs are not silently rewritten. Same-name/same-type
homonyms need additional disambiguation; explicit aliases must be trustworthy.
These are documented identity limitations rather than a claim of perfect entity
resolution.

## Evidence, quality and filtering

The validator checks for a literal quote first. When it can verify an equivalent
prose span, it also accepts omitted CommonMark emphasis and inline link markup
while retaining the link label. It preserves case, punctuation, escapes, and
inline code syntax. Extraction records the match kind, zero-based character
start, end-exclusive offset, and exact raw Markdown in `evidence_span`. Accepted
rows and stored graph evidence use the original source text. The existing
ingestion path also recognizes whitespace-only variants of prose quotes.

A match establishes provenance. Acceptance requires a complete, affirmative
top-level prose assertion with the expected predicate and direction. A supported
predicate can connect one named subject to a coordinated object list or a
coordinated subject list to one named object. Each list member must be a
grounded entity. Disjunctions, compound clauses with separate predicates,
negation, speculation, questions, and ambiguous lists on both sides are
flagged. Source context is also checked for contradictory statements.

The deterministic English predicate vocabulary includes “uses”, “depends on”,
“supports”, “based on”, “built on”, “builds upon”, and the inverse construction
“B is the foundation of A” for A BASED_ON B. Indirect claims and paraphrases
remain unverified. Source validation checks the assertion in the supplied
text. Factual correctness still depends on the source.

Importance starts from a generic relation-specific baseline:

| Relation | Base importance |
| --- | ---: |
| BASED_ON, DEPENDS_ON | 0.90 |
| SUPPORTS, IMPLEMENTS, REQUIRES | 0.85 |
| USES, EXTENDS, PART_OF, PROVIDES | 0.80 |
| INTEGRATES_WITH | 0.75 |
| EXAMPLE_OF | 0.30 |
| MENTIONS | 0.15 |

Add 0.05 when topic terms overlap the endpoints; cap at 1.0. Halve importance for
explicit incidental context such as “in an example” or “for illustration”. Confidence is 0.90
only after deterministic grounding passes. Optional model estimates may lower
these scores but cannot raise them or bypass grounding. Repeated statements do
not inflate confidence. Canonical edges aggregate maximum importance and maximum
confidence from their surviving accepted evidence records. These values remain
experimental heuristics, not calibrated probabilities or validated usefulness
measurements.

`GraphPolicy` is the single configuration point:

```python
GraphPolicy(
    min_confidence=0.75,
    default_importance_threshold=0.60,
    default_expansion_limit=5,
    max_expansion_limit=50,
    importance_weight=0.6,
    confidence_weight=0.4,
    context_weight=0.2,
)
```

Unsupported/low-confidence relationships do not enter the trusted edge set.
Accepted low-importance relationships remain stored, including their evidence;
the default expansion threshold hides them. Lowering `min_importance` reveals
them. Every assessed relation returns an accepted/rejected `Decision` with reason
codes and scores. Neo4j persists these decisions as a JSON string on its source
chunk, and evidence records retain policy version. Replacing a chunk updates that
chunk's audit; this is a current-state audit, not an immutable historical ledger.

## Incremental ingestion and storage

One chunk is the transaction/update unit. Its hash covers text, document, URL and
topic; processing also records extractor/provider/prompt version and policy
fingerprint. Unchanged inputs skip extraction and writes. Changing provider/model
configuration must change `provider_version`; changing rule semantics requires a
policy version bump. Pre-extracted payload revisions are hashed directly.

LLM calls occur outside retryable transactions. A transaction rechecks the cache,
normalizes entities, replaces that chunk's previous evidence, deduplicates
canonical directed edges and recalculates affected edge counts/scores. If a chunk
changes, stale support is removed; edges supported by other chunks survive. An
edge with no remaining evidence is removed to avoid retaining unsupported trusted
knowledge. Rejected knowledge is preserved in the decision audit, not as a trusted
edge. No importance-based deletion occurs.

The offline store has indexes by project/name/type, adjacency, relationship and
chunk evidence. It snapshots state for rollback and is intended for small graphs
and tests, not production-scale durability.

Neo4j uses:

```text
(:Entity)-[:RELATIONSHIP {relationship_id, project_id, relation_type,
                         importance, confidence, evidence_count, verified}]->(:Entity)
(:Entity)-[:HAS_NAME]->(:EntityName)
(:SourceChunk {project_id, chunk_id, document_id, url, text, content_hash, ...})
(:Evidence {project_id, evidence_id, relationship_id, chunk_id, document_id,
            url, text, content_hash, importance, confidence, policy_version})
(:KnowledgeProject {project_id, revision, write_lock})
```

Evidence nodes refer to their canonical edge through its scoped ID. This keeps
the actual Entity-to-Entity graph simple without attempting nested-object edge
properties or duplicating edge properties into a second relationship-node model.
Name nodes provide indexed alias/compact-name candidate lookup. Composite
uniqueness constraints protect entities, names, chunks, evidence and directed
canonical edge IDs. Evidence lookups have project/edge and project/chunk indexes.

`ensure_schema()` applies the additive, idempotent migration; it does not drop
existing data. This schema requires Neo4j 5.7+ relationship uniqueness support.
Managed driver transactions serialize writes per project via a project-node write
lock. This favors correct incremental alias/evidence updates over parallel writes
within one workspace. See the official [transaction documentation](https://neo4j.com/docs/python-manual/current/transactions/)
and [constraint syntax](https://neo4j.com/docs/cypher-manual/5/constraints/syntax/).

## Ranked expansion, API and pagination

Default eligibility requires verified evidence, confidence >= 0.75 and importance
>= 0.60. Default ranking is `0.6 * importance + 0.4 * confidence`. With context,
add `0.2 * relevance` and divide by the weight sum. Relevance is the fraction of
query terms present in the neighboring entity's name, aliases or description.
No LLM/embedding call occurs. Ties sort by stable edge ID.

Neo4j starts from an indexed center lookup, applies scoped filters, computes
scores, orders and fetches only `limit + 1` rows. It does not transfer the full
neighborhood to Python. The database still needs to inspect/sort eligible adjacent
relationships; production degree-dependent latency has not been benchmarked.
Evidence details are fetched separately and are paginated too.

```http
GET /api/graph/nodes/{entity_id}/expand?project_id=demo
GET /api/graph/nodes/{entity_id}/expand?project_id=demo&limit=10&min_importance=0.6&min_confidence=0.75&context=async%20await
GET /api/graph/nodes/{entity_id}/expand?project_id=demo&cursor={next_cursor}
GET /api/graph/edges/{relationship_id}/evidence?project_id=demo&limit=5
GET /api/graph/config
```

The response includes a separate center node, unique neighbor nodes, stable
directed edges with both scores and evidence count, and pagination. Evidence
responses additionally include source/target node labels and original quote,
document ID, chunk ID, source URL and content hash. See the generated evaluation
report's `example_expansion_response` and `example_evidence_response` for actual
response objects.

Parameters and finite score ranges are validated; missing nodes are 404, invalid
queries/cursors are 422, changed-graph cursors are 409, and database unavailability
is 503. Repeated/unknown query parameters are rejected. Keyset cursors bind project,
node, filters/context and policy to the graph revision. A graph update invalidates
old pages instead of silently returning duplicate edges after score changes.
The client must keep filters/context the same on subsequent pages. Cursors are
opaque positions, not authorization tokens.

All data access includes explicit project scope. Authentication was out of scope
and absent: a deployment must bind/check `project_id` against its authenticated
workspace before mounting this adapter. The included server binds localhost and
is a development entry point, not a deployment/authentication system.

## Frontend integration contract

There is no frontend graph library, UI, design system, node-position state or
relationship-details panel in this repository, so no existing interface could be
updated or visually tested. No replacement frontend was built.

The future frontend should read defaults/limits from `/api/graph/config`, keep
nodes/edges in maps keyed by stable IDs, merge returned records, and retain
existing coordinates. Keep one pending request per center/query, expose loading
and errors, retain `next_cursor` per expansion, and use it for “Load more”.
Changing Top-K/importance/confidence/context resets the relevant cursor; a 409
also resets pagination. Inspect an edge using its evidence endpoint rather than
generating explanations. Top 5/10/20 controls and score sliders can bind directly
to these API parameters. Repeated first-page requests return the same IDs and
later pages do not repeat edges in an unchanged graph; the future client still
needs ID-based merging across different center nodes. Frontend behavior is not
claimed to be implemented or tested.

## Tests, evaluation and limitations

```bash
python -m pip install -e ".[test,graph]"
python -m pytest -q
python -m knowledge.evaluation --output output/graph-quality/evaluation.json
```

The Neo4j test requires `GRAPH_TEST_NEO4J=1` plus `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, optionally `NEO4J_DATABASE`. It creates a unique test project,
checks repeated ingestion, multiple evidence, ranking, updates and isolation,
then removes only that test project. Offline Cypher tests verify query
parameterization, filters, bounds and migration constraints; they do not prove
database execution or Cypher planning. The live test is skipped when not configured.

Executed validation on this workspace:

| Check | Actual result |
| --- | --- |
| Full pytest suite | 105 passed, 1 skipped; exit code 0 |
| Live Neo4j integration | Skipped: no configured server/installed driver |
| Labeled synthetic sample | 17 decisions: 11 accepted, 6 rejected |
| Canonical output | 12 entities, 9 directed edges |
| Duplicate entity/edge rates | 0 / 0 on this sample |
| Incorrect merges | 0 against the sample's entity groups |
| Evidence-validation pass rate | 11/17 = 64.71% |
| Accepted-relationship precision | 11/11 = 100% on this sample |
| Expansion Precision@5 | 5/5 = 100% on this sample |
| Wheel build | Passed; current sources, migration and fixture verified in archive |
| Existing crawler/cleaning files | Unmodified; existing regression tests pass |

The installed `pyreadline3` emits a Windows console cleanup warning after pytest;
the test process exits successfully. The wheel build also reports an environment
warning about the installed `packaging` version; the archive builds and verifies.

The 17-record synthetic sample includes useful relationships, incidental mentions,
aliases, duplicate relationships, distinct React/React Native and Python/asyncio
concepts, heading noise, wrong predicates, fabricated/missing evidence, negation
and a missing source chunk. Labels are authored for regression, not an
independently annotated accuracy study. The harness reports duplicate entity/edge
rates, incorrect merges, evidence-validation pass rate, accepted relationship
precision, label agreement and expansion Precision@5 (fixed denominator 5).

Actual sample outcome is generated, not hard-coded into the harness: 12 canonical
entities, 9 directed canonical relationships from 11 accepted extractions;
6 rejected extractions. Two duplicate accepted edge instances accumulate extra
evidence rather than extra graph edges. Unfiltered FastAPI has seven canonical
neighbors, including incidental Uvicorn; default expansion selects five:
Starlette, Async/Await, HTTP, OpenAPI and Pydantic. Uvicorn remains stored and can
be inspected by lowering importance. Dependency Injection is useful too and is
available on the next page; it is omitted from Top-5 because the current ranking
has a deterministic cutoff, not because it is invalid.

Known limits: no configured/real LLM run; no available/live-tested Neo4j server;
no existing frontend to integrate; English predicate rules with intentionally
limited recall; no general semantic truth checker or cross-document contradiction
resolution; aliases require trustworthy extraction; homonyms may need manual
disambiguation; no version-history ledger or deletion-of-entire-document API.
Per-project writes are serialized, and offline rollback snapshots are not a large
graph storage strategy. Additional independently labeled real documentation,
recall measurements and actual Neo4j profiling are needed before interpreting
these toy metrics as production quality.
