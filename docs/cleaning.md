# Document cleaning

This stage accepts raw crawler documents and returns clean documents. It works
on existing files, needs no browser or network, and does not perform chunking,
entity/relation extraction, embeddings, or graph processing.

## Architecture and files

The existing crawler package remains the architecture boundary:

| File | Purpose |
| --- | --- |
| `crawler/cleaning/__init__.py` | Public cleaning API |
| `crawler/cleaning/models.py` | Pydantic input/output models extending the existing `Document` fields |
| `crawler/cleaning/cleaner.py` | `DocumentCleaner.clean()` and `clean_document()`; isolated output and debug counts |
| `crawler/cleaning/markdown_cleaner.py` | Source-span cleanup and heading helper |
| `crawler/cleaning/noise.py` | Small generic vocabulary and whole-block UI detection |
| `crawler/cleaning/text_cleaner.py` | Conservative secondary-text cleanup using existing `collapse_text()` |
| `crawler/cleaning/__main__.py` | Saved JSON-to-JSON command |
| `crawler/cleaner.py` (updated) | Compatibility exports used by the existing crawl pipeline |
| `tests/test_cleaning.py` | Synthetic regressions, metadata isolation, CLI and crawler compatibility |
| `tests/test_cleaning_real_data.py` | Integration checks using six actual saved crawler pages |
| `scripts/verify_cleaning.py` | Repeatable verification and separate cleaned outputs |
| `pyproject.toml` (updated) | `markdown-it-py`, pytest test extra, and explicit crawler package discovery |
| `README.md` (updated) | API, CLI and verification commands |

No website-specific rules are used. Markdown is parsed with CommonMark to locate
source spans, then the original source is edited directly; rendering does not
replace the document. The existing crawler API and its output schema are unchanged.

## Input and output schemas

`RawDocument` and `CleanDocument` expose the same required fields:

```python
url: str
title: str
markdown: str
text: str
metadata: dict[str, Any]
```

The cleaner accepts these models, the crawler's existing `Document`, or a JSON
mapping. Extra top-level fields and unknown metadata keys are retained. Metadata
is deeply copied; cleaning does not mutate the source. JSON timestamp strings
stay strings; when an existing crawler model is supplied, its datetime values
remain datetime values until JSON serialization. The original `hash` is preserved
as crawl provenance and is not recalculated as a cleaned-document hash.

Markdown remains authoritative even when empty; text never reconstructs it.
No new metadata is inserted. `extract_headings(markdown)` returns frozen
`Heading(level, title, line)` records, with inline Markdown titles and one-based
line numbers, for future section-aware consumers. It does not create chunks.

## Cleaning rules

1. **Whitespace:** normalize CRLF/CR to LF outside protected source spans, remove
   trailing space/tab noise, collapse repeated blank lines to one blank line,
   and trim surrounding empty lines. Keep indentation and internal spacing.
   Two trailing spaces represent a Markdown hard break and are retained as two.
2. **Heading permalinks:** remove only a final `[¶](...)` link from parsed
   headings, including optional URL titles, balanced URL parentheses, Setext
   headings, and optional ATX closing hashes. Keep heading text and level.
   Ordinary prose and meaningful heading links remain unchanged.
3. **Navigation:** remove a top-level paragraph only when every line is one of
   `Back to top`, `Previous`, `Next`, `Edit this page`, `Share`, `Copy page`, or
   `Table of contents`, or a single link with exactly that label. Matching is
   case-insensitive. Lists, quotes, headings, code, and paragraphs mixing UI
   words with explanations are preserved. Links with substantive titles such
   as `Previous releases` remain intact. Unresolved reference-style UI links
   are kept conservatively.
4. **Duplicates:** collapse immediately adjacent, identical ATX heading lines.
   Navigation removed between such lines does not prevent their collapse.
   Blank-separated headings, repeated paragraphs, repeated list items, code,
   and repeated sections are preserved because their contexts may differ.
   There is no semantic deduplication.
5. **Code:** keep fenced, tilde-fenced, nested, indented, and unclosed code block
   source verbatim, including blank lines, trailing spaces, and original line
   endings. Protect multiline inline-code paragraphs as well. Inline-code
   spacing is never normalized.
6. **HTML:** preserve raw HTML and its content rather than stripping tags.
   An HTML parser tracks wrappers across blank lines so paragraphs inside a
   layout or semantic wrapper cannot be mistaken for standalone navigation.
   Ambiguous or unclosed wrappers are kept conservatively. No image download
   or HTML-to-text conversion occurs here.
7. **Meaningful structure:** retain links, images/alt text, tables, notes,
   warnings, lists, emphasis, documentation references, technical names and
   relational prose. No link deletion based on destination domain or URL.
8. **Secondary text:** normalize line endings and paragraph whitespace using
   the existing text utility; remove only whole blocks of exact plain UI labels.
   Text without reliable paragraph boundaries is deliberately kept conservative.
   It is not used to modify Markdown.

The UI vocabulary is a conservative English baseline; multilingual UI labels,
menus mixed with prose, and arbitrary HTML UI can remain. Additional generic
rules can be added in the isolated noise module with preservation regressions.

Debug logging includes lengths and counts for removed navigation blocks,
heading anchors, duplicate headings, and changed whitespace lines. It does not
log document content, metadata, or URLs that might contain credentials/query tokens.

## Verification and artifacts

```bash
python -m pytest -q
python -m scripts.verify_cleaning
python -m crawler.cleaning output/page0006.json output/cleaned/page0006.json
```

The standalone cleaner rejects identical input/output paths. The verifier writes
`output/cleaned/page0001.json` through `page0006.json` and
`output/cleaned/verification.json`, keeping the original crawler files in place.
The six real-data tests require the supplied `output/page0001.json` through
`page0006.json`; these are local integration inputs, not network fetches.

Validation completed with Python 3.12.4: **67 tests passed**, including all six
real crawler pages. The saved-JSON CLI also passed, and the wheel built
successfully with all seven cleaning modules and no crawler-output files inside.

For the supplied `https://fastapi.tiangolo.com/async/` crawl:

| Check | Before | After |
| --- | ---: | ---: |
| Markdown characters | 24,491 | 22,822 |
| Heading count / hierarchy | 21 | 21, same levels and text |
| Code blocks | 8 | 8, identical source spans |
| Meaningful links | 15 | 15, same destinations and occurrence counts |
| Images | 13 | 13, same source URLs and occurrence counts |
| `async` in visible text/code | 59 | 59 |
| `await` in visible text/code | 28 | 28 |
| `FastAPI` | 17 | 17 |
| `Starlette` | 3 | 3 |
| `AnyIO` | 4 | 4 |
| `asyncio` in visible text/code | 1 | 1 |

Technical-word counts exclude link destinations: deleting heading permalink URLs
otherwise reduces raw substring counts of `async`/`await` even though every word
in the document content survives. The verifier also checks metadata, URL/title,
parsing with table support, footer removal, and exact document idempotency.

Before, from the actual first heading:

```markdown
# Concurrency and async / await[¶](https://fastapi.tiangolo.com/async/#concurrency-and-async-await "Permanent link")
```

After:

```markdown
# Concurrency and async / await
```

The following explanatory paragraph and all eight code examples remain intact.
The final standalone `Back to top` is removed.
