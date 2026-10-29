"""Regression coverage for conservative, structure-aware document cleaning."""

import logging
import json
import sys
from copy import deepcopy

import pytest
from markdown_it import MarkdownIt
from pydantic import ValidationError

from crawler.cleaning import (
    CleanDocument, DocumentCleaner, RawDocument, clean_document,
    clean_markdown, clean_text, extract_headings,
)
from crawler.models import Document


def raw_document(markdown: str = "", text: str = "") -> dict:
    return {
        "url": "https://docs.example/guide?token=secret",
        "title": "Guide", "markdown": markdown, "text": text,
        "metadata": {
            "depth": 1, "parent": "https://docs.example/", "domain": "docs.example",
            "crawl_time": "2026-09-10T11:54:10Z", "language": "en", "hash": "raw-hash",
            "original_url": "https://docs.example/guide",
            "normalized_url": "https://docs.example/guide", "custom": {"tags": ["api"]},
        },
        "custom_top_level": {"keep": True},
    }


@pytest.mark.parametrize(("source", "expected"), [
    ('## async and await[¶](https://example.com/async)', '## async and await'),
    ('## How to use FastAPI [¶](https://example.com "Permanent link")',
     '## How to use FastAPI'),
    ('### `async` [¶](https://example.com/a_(b)) ###', '### `async` ###'),
    ('Title [¶](https://example.com)\n=====', 'Title\n====='),
    ('> ## Heading [¶](https://example.com)', '> ## Heading'),
    ('Paragraph [¶](https://example.com)', 'Paragraph [¶](https://example.com)'),
    ('## [Reference](https://example.com)', '## [Reference](https://example.com)'),
    ('## Literal `[¶](https://example.com)`', '## Literal `[¶](https://example.com)`'),
    ('## Keep [¶](https://example.com) inside heading',
     '## Keep [¶](https://example.com) inside heading'),
    ('## Escaped \\[¶](https://example.com)', '## Escaped \\[¶](https://example.com)'),
])
def test_heading_anchor(source: str, expected: str) -> None:
    assert clean_markdown(source) == expected


@pytest.mark.parametrize("code", [
    '```python\n@app.get("/")\nasync def hello():\n    return {"hello": "world"}\n```',
    '```python\n# Keep [¶](https://example.com)\nx = 1  \n\n\n\nPrevious\n```',
    '~~~~python\nx = "```"\n\tNext  \n\n\n~~~~',
    '````markdown\n```python\n# Inner\n```\n\n\n````',
    '    # Indented code  \n    Previous\n\n    Next  \n',
    '```python\r\nx = 1  \r\n\r\n\r\n```\r\n',
    '```python\rprint(1)  \r\r\r```\r',
    '```python\n# unclosed fence\nPrevious  \n\n\n',
    '```text\na\u2028b\x0bc  \n\n\n```',
    '- Example:\n\n  ```python\n  Next  \n\n\n  ```',
    '> ```python\n> Previous  \n>\n>\n> ```',
])
def test_preserve_code_verbatim(code: str) -> None:
    assert code in clean_markdown('## Example\n\n' + code)


def test_entities_and_meaningful_links_images_notes_tables_lists() -> None:
    source = '''# H1
## H2
### H3

FastAPI is based on Starlette and uses Pydantic.

- [Starlette](https://www.starlette.io/)
- [Previous releases](https://docs.example/releases)
  - nested `inline  code`
- Next

1. First
2. Second

**bold** and `inline code` and <https://example.com>.

![Concurrency](https://example.com/concurrency.png)

> Warning: preserve this.
> Next

!!! note
    Keep this note.

| Entity | Dependency |
| --- | --- |
| FastAPI | Starlette |

[docs]: https://example.com/reference

See [docs] and [Python docs](https://docs.python.org/3/).
'''.rstrip()
    assert clean_markdown(source) == source


@pytest.mark.parametrize("navigation", [
    'Previous\nNext', '[Previous](https://example.com/prev)\n[Next](/next)',
    'Back to top', 'Edit this page', 'Share', 'Copy page', 'Table of contents',
])
def test_navigation_noise(navigation: str) -> None:
    source = navigation + '\n\n# Introduction\n\nFastAPI is a web framework.'
    assert clean_markdown(source) == '# Introduction\n\nFastAPI is a web framework.'


@pytest.mark.parametrize("source", [
    '# Next\n\nAn explanation of Next.',
    'Next\nmeans the successor in this example.',
    '[Next.js](https://nextjs.org/)',
    '[Next: Async programming](/async)',
    '- Next\n- Previous',
    '> Share\n> Previous',
    '[Previous][ref]\n\n[ref]: /previous',
    'Use the Next and Previous buttons to navigate.',
    '`Previous`',
])
def test_ambiguous_navigation_is_preserved(source: str) -> None:
    assert clean_markdown(source) == source


def test_whitespace_and_hard_breaks() -> None:
    assert clean_markdown('\r\nHello \r\n\r\n\r\n   \r\nWorld\t\r\n') == 'Hello\n\nWorld'
    source = 'Line one    \nLine two\\\nLine three'
    cleaned = clean_markdown(source)
    assert cleaned == 'Line one  \nLine two\\\nLine three'
    parser = MarkdownIt()
    breaks = lambda value: [child.type for token in parser.parse(value)
                            for child in token.children or [] if child.type == 'hardbreak']
    assert breaks(source) == breaks(cleaned) == ['hardbreak', 'hardbreak']


@pytest.mark.parametrize("source", [
    '<div class="layout">\n\nPrevious\n\n<strong>Important</strong>\n</div>',
    '<pre>\nx = "<tag>"  \n\n\n</pre>',
    '<table><tr><td>FastAPI</td><td>Starlette</td></tr></table>',
    '<details>\n<summary>Note</summary>\nNext\n</details>',
    'Use <kbd>Ctrl</kbd> and <https://example.com>.',
])
def test_html_is_preserved_without_blind_tag_removal(source: str) -> None:
    assert clean_markdown(source) == source


def test_deduplication_is_limited_to_adjacent_headings() -> None:
    assert clean_markdown('# A\n# A\n# A') == '# A'
    for source in ('# A\n\n# A', 'Repeat.\n\nRepeat.', '- item\n- item',
                   '# A\n\nRepeat.\n\n# B\n\nRepeat.'):
        assert clean_markdown(source) == source


def test_schema_metadata_extras_and_input_are_preserved() -> None:
    raw = raw_document('# Guide [¶](https://docs.example/guide)', 'Hello  world')
    original = deepcopy(raw)
    cleaned = clean_document(raw)
    assert isinstance(cleaned, CleanDocument)
    assert cleaned.markdown == '# Guide'
    assert cleaned.text == 'Hello world'
    assert raw == original
    for key in ('url', 'title', 'metadata', 'custom_top_level'):
        assert cleaned.model_dump()[key] == raw[key]
    cleaned.metadata['custom']['tags'].append('changed')
    assert raw == original


def test_crawler_and_raw_models_are_accepted() -> None:
    data = raw_document('# Example')
    crawler_document = Document.model_validate(data)
    cleaned = DocumentCleaner().clean(crawler_document)
    assert cleaned.metadata == crawler_document.metadata.model_dump()
    assert clean_document(RawDocument.model_validate(data)).markdown == '# Example'


@pytest.mark.parametrize('markdown', ['', '\n \t\n', '# A\nPrevious\n# A',
                                      '# A\n# A\n\nNext',
                                      'Line   \n\n\nWorld',
                                      '```\r\ncode  \r\n\r\n\r\n```\r\n'])
def test_empty_and_idempotency(markdown: str) -> None:
    first = clean_document(raw_document(markdown))
    assert clean_document(first) == first
    assert clean_document(raw_document()).markdown == ''
    assert clean_document(raw_document()).text == ''


def test_text_is_secondary_and_conservative() -> None:
    assert clean_text('Previous\nNext\n\nHello  world\r\n\r\n\r\nBack to top') == 'Hello world'
    assert clean_text('Next\nexplains the successor.') == 'Next\nexplains the successor.'
    assert clean_text('FastAPI uses Starlette.').startswith('FastAPI uses Starlette.')
    assert clean_document(raw_document('', '# Text is not Markdown')).markdown == ''


def test_heading_helper_preserves_hierarchy_and_ignores_code() -> None:
    source = '# Root\n\n## Child\n\n```\n# Not a heading\n```\n\nSetext\n------'
    assert [(h.level, h.title, h.line) for h in extract_headings(source)] == [
        (1, 'Root', 1), (2, 'Child', 3), (2, 'Setext', 9),
    ]


def test_logging_does_not_include_content_or_secrets(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger='crawler.cleaning.cleaner'):
        clean_document(raw_document('# private document content'))
    assert 'markdown length' in caplog.text
    assert 'private document content' not in caplog.text
    assert 'secret' not in caplog.text
    assert 'raw-hash' not in caplog.text


def test_required_crawler_fields_are_validated() -> None:
    with pytest.raises(ValidationError):
        clean_document({'markdown': 'Hello'})


def test_standalone_cli_preserves_raw_json(tmp_path, monkeypatch) -> None:
    from crawler.cleaning.__main__ import main

    source, target = tmp_path / 'raw.json', tmp_path / 'clean' / 'page.json'
    data = raw_document('# Intro [¶](https://example.com)')
    source.write_text(json.dumps(data), encoding='utf-8')
    original = source.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['cleaning', str(source), str(target)])
    main()
    assert source.read_bytes() == original
    assert json.loads(target.read_text(encoding='utf-8')) == clean_document(data).model_dump()
    monkeypatch.setattr(sys, 'argv', ['cleaning', str(source), str(source)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


