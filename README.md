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

The command writes `page0001.json`, etc. and `index.json` to the output directory. The package deliberately does not create embeddings or perform entity/graph processing.

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
