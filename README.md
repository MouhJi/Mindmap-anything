# Universal Documentation Crawler

An asynchronous, configuration-free crawler for modern documentation sites. It renders JavaScript using Crawl4AI/Playwright, discovers internal documentation links with DOM heuristics, extracts cleaned Markdown, and writes one JSON document per page.

## Install

```bash
python -m pip install -e .
playwright install chromium
```

## Run

```bash
docs-crawl https://fastapi.tiangolo.com/ --max-depth 3 --max-pages 100 --output-dir output
```

The command writes `page0001.json`, etc. and `index.json` to the output directory.
The crawler command only crawls and cleans; knowledge processing is a separate,
optional stage consuming already prepared source chunks.

## Document cleaning

`crawler.cleaning` provides a standalone, conservative cleaning stage for existing
crawl JSON or `crawler.models.Document` instances. The crawler's existing
`clean_markdown` / `clean_text` imports delegate to this same implementation.

```python
import json
from pathlib import Path
from crawler.cleaning import DocumentCleaner, extract_headings

raw = json.loads(Path("output/page0006.json").read_text(encoding="utf-8"))
cleaned = DocumentCleaner().clean(raw)
headings = extract_headings(cleaned.markdown)
```

To clean a saved page without crawling or starting a browser:

```bash
python -m crawler.cleaning output/page0006.json output/cleaned/page0006.json
```

Markdown is the primary representation. Code source, inline code, headings,
lists, tables, images, meaningful links, and crawler metadata are preserved.
Rules are site-independent and intentionally prefer keeping ambiguous content.
See [cleaning details](docs/cleaning.md) for schemas, rules, limitations, and the
file manifest.

Install test dependencies and run regression tests plus real-crawl verification:

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m scripts.verify_cleaning
```

The verifier compares all six existing `output/page*.json` files with cleaned
versions, checks headings, exact code spans, links/images, technical words,
metadata and idempotency, then writes separate pages and `verification.json`
under `output/cleaned/`.

## Knowledge quality and node expansion

The independent `knowledge` package adds validated structured extraction,
conservative entity normalization, evidence validation, canonical edge/evidence
deduplication, quality scores, and bounded graph expansion. Section-aware
chunking feeds the existing `StructuredExtractor`. The optional Gemini adapter
supports asynchronous structured extraction and an auditable batch runner.

Install the adapter with `python -m pip install -e ".[llm,test]"` and set
`GEMINI_API_KEY` and `GEMINI_MODEL` in the process environment. See the
[FastAPI extraction pilots](evaluation/real_world/README.md#gemini-extraction)
for the live smoke test, five- and twenty-chunk selections, and report formats.

```python
from knowledge.ingestion import KnowledgePipeline
from knowledge.models import ExtractionResult, SourceChunk
from knowledge.repository import InMemoryRepository
from knowledge.expansion import ExpansionService

repository = InMemoryRepository()  # offline/testing; use Neo4jRepository for persistence
pipeline = KnowledgePipeline(repository)
source = SourceChunk(
    project_id="demo", chunk_id="chunk-1", document_id="document-1",
    url="https://docs.example/guide", text="FastAPI is based on Starlette.",
    topic="FastAPI",
)
extraction = ExtractionResult.model_validate({
    "entities": [{"name": "FastAPI", "type": "Framework"},
                 {"name": "Starlette", "type": "Framework"}],
    "relationships": [{"source": "FastAPI", "target": "Starlette",
                       "relation_type": "BASED_ON", "chunk_id": "chunk-1",
                       "evidence": "FastAPI is based on Starlette."}],
})
report = pipeline.ingest_chunk(source, extraction)
center = repository.find_entities("demo", "Framework", ["fastapi"])[0]
page = ExpansionService(repository).expand("demo", center.entity_id)
```

Evaluate the labeled synthetic sample without an LLM or database:

```bash
python -m knowledge.evaluation --output output/graph-quality/evaluation.json
```

For Neo4j persistence, install `.[graph]`, configure `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD` (and optionally `NEO4J_DATABASE`), then run:

```bash
python -m knowledge.api --init-schema --port 8000
```

This starts a local WSGI read API, including:

```http
GET /api/graph/nodes/{entity_id}/expand?project_id=demo
GET /api/graph/edges/{relationship_id}/evidence?project_id=demo
GET /api/graph/config
```

See [knowledge quality architecture, schemas, scoring, API, test instructions,
and limitations](docs/knowledge-quality.md). Live Neo4j tests are opt-in with
`GRAPH_TEST_NEO4J=1`; offline tests do not imply a working database connection.

## GraphRAG frontend demo

The independent `frontend/` workspace uses React, TypeScript, Vite, React Flow,
and Lucide icons. It does not change or start the Python pipeline and requires no
API keys, Neo4j, crawler, or LLM. Frontend development requires Node.js
**22.18+** and **pnpm 11.25.0**, pinned in `frontend/package.json`.

On Windows, install the pinned pnpm version once if needed.

```powershell
npm install --global pnpm@11.25.0
```

Run these commands from the repository root.

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

`frontend/pnpm-lock.yaml` records the resolved dependencies. The install permits
the locked esbuild version's postinstall script via `frontend/pnpm-workspace.yaml`.

Open the Local URL printed by Vite (normally `http://127.0.0.1:5173`). The server
binds to loopback only. Nothing is published. To build and preview production
assets locally:

```powershell
pnpm build
pnpm preview
```

The Vietnamese learning workspace includes:

- A 12-node LangChain graph, five additional nodes available through bounded
  expansion, direct-neighbour highlighting, search, type filters, pan, zoom,
  fit-to-view, and a focus mode. Use Tab and Enter to choose nodes. Search accepts
  Enter to reveal the first matching node; Escape exits focus mode and drawers.
- Node explanations, collapsible illustrative Python examples, valid reading
  references, and actions to expand, ask a question, or add a note.
- Contextual **simulated chat**, suggested questions, links back to graph nodes,
  Enter to send, and Shift+Enter for a new line. Mobile/tablet chat opens in a
  drawer with a focus trap, Escape support, and focus restoration.
- A source library and editable notes. Notes autosave to this browser's
  `localStorage` (`graphrag.demo.notes.v1`) and survive navigation, graph
  regeneration, and reload. Storage errors keep current text in memory and show
  an actionable message. Copy notes elsewhere when storage is unavailable.
- JSON export of the current graph, including expanded nodes. The export has
  `schemaVersion`, `isMock`, `requestedUrl`, `nodes`, `edges`, and `sources`;
  it excludes notes and chat history. Search/type filters affect the view only,
  so export retains every loaded node.

All graph content, excerpts, examples, and chat responses are authored demo
material. References are reading links, **not evidence retrieved by this app**.
A valid HTTP(S) URL loads the same sample and is recorded only as `requestedUrl`.
No request is sent to that URL. Creating a new graph resets selection, expansion,
filters, viewport, and chat while preserving notes. No quality/confidence/crawl
measurements are invented.

### Frontend structure and backend integration

- `frontend/src/data/langchain.ts`: sample nodes, edges, reference sources.
- `frontend/src/types.ts`: frontend contracts and `GraphService` interface.
- `frontend/src/services/graph.ts`: demo `getGraph`, `createGraphFromUrl`,
  `expandNode`, `askGraph`, idempotent merging, validation, and JSON serialization.
- `frontend/src/services/chat.ts`: deterministic contextual reply generation.
- `frontend/src/services/backendAdapter.ts`: opt-in read adapter matching
  `knowledge/api.py` and `knowledge/models.py`, including paginated expansion and
  evidence URLs. It is **not enabled** in the demo. Real and mock provenance are
  kept separate. Node types are mapped to the three presentation categories.
- `frontend/src/utils/storage.ts`: guarded notes persistence.
- `frontend/src/components/`: shell navigation, URL form, graph, node details,
  sources, notes, and chat UI; `src/hooks/` holds responsive/focus utilities.

To connect a backend later, inject/replace the `GraphService` implementation
imported by `App.tsx`. The existing Python API provides expansion, edge evidence,
and config only. Initial graph loading, crawl/job creation, rich node descriptions,
and chat still require backend contracts; this frontend does not invent those
endpoints. For real data initialize a separate `isMock: false` graph, map API
expansions, and fetch evidence as real sources. Use a same-origin proxy or
deliberately configured CORS/authentication at integration time; do not put
database credentials or provider keys into the browser. Content is rendered as
plain React text, never uncontrolled HTML.

### Frontend checks

```powershell
cd frontend
pnpm test
pnpm build
```

Tests use Node's built-in runner with TypeScript stripping (no additional test
framework). They cover graph/source integrity, URL validation, bounded and
idempotent expansion, dangling edges, regeneration, contextual/limited chat,
export privacy, notes restoration/storage failures, and adapter provenance.
See [frontend verification](docs/frontend-verification.md) for the recorded
manual desktop/mobile checks and limitations.
