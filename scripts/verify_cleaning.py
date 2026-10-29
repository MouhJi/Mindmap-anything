"""Verify existing crawl JSON and write separate cleaned pages plus a report.

Run from the repository root: python -m scripts.verify_cleaning
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from markdown_it import MarkdownIt

from crawler.cleaning import clean_document

ENTITIES = ("async", "await", "FastAPI", "Starlette", "AnyIO", "asyncio")


def _headings(tokens: list) -> list:
    result = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        children = list(tokens[index + 1].children or [])
        if ([child.type for child in children[-3:]] == ["link_open", "text", "link_close"]
                and children[-2].content == "¶"):
            children = children[:-3]
        result.append((token.tag, "".join(child.content for child in children).rstrip()))
    return result


def _code_source(markdown: str, tokens: list) -> list[str]:
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", markdown)
    return ["".join(lines[token.map[0]:token.map[1]]) for token in tokens
            if token.type in {"fence", "code_block"}]


def _links(tokens: list) -> Counter:
    links = Counter()
    for token in tokens:
        children = token.children or []
        for index, child in enumerate(children):
            if child.type == "link_open":
                # Exclude only heading permalink/UI labels, not references.
                end = index + 1
                label = []
                while end < len(children) and children[end].type != "link_close":
                    label.append(children[end].content)
                    end += 1
                if "".join(label).strip() not in {"¶", "Back to top"}:
                    links[("link", child.attrGet("href"))] += 1
            elif child.type == "image":
                links[("image", child.attrGet("src"))] += 1
    return links


def _content(tokens: list) -> str:
    # Count documentation words in visible text and code, excluding link URLs.
    # Heading permalink URLs themselves contain words such as async and await.
    return "\n".join(
        token.content if token.type in {"fence", "code_block", "html_block"} else
        "".join(child.content for child in token.children or []
                if child.type in {"text", "code_inline", "html_inline", "image"})
        for token in tokens if token.type in {"inline", "fence", "code_block", "html_block"}
    )


def verify_document(raw: dict) -> tuple[dict, dict]:
    """Compare source spans and parsed structure; raise on information loss."""
    cleaned = clean_document(raw)
    output = cleaned.model_dump(mode="json")
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    before, after = parser.parse(raw["markdown"]), parser.parse(cleaned.markdown)
    checks = {
        "headings_and_hierarchy_preserved": _headings(before) == _headings(after),
        "code_source_preserved_verbatim": (
            _code_source(raw["markdown"], before) == _code_source(cleaned.markdown, after)
        ),
        "meaningful_links_and_images_preserved": _links(before) == _links(after),
        "metadata_preserved": output["metadata"] == raw["metadata"],
        "url_and_title_preserved": (output["url"], output["title"]) == (raw["url"], raw["title"]),
        "idempotent": clean_document(cleaned) == cleaned,
        "markdown_parseable": bool(after) or not cleaned.markdown,
        "navigation_footer_removed": not cleaned.markdown.endswith("\n\nBack to top"),
    }
    original_content, cleaned_content = _content(before), _content(after)
    entity_counts = {
        entity: {"before": original_content.count(entity), "after": cleaned_content.count(entity)}
        for entity in ENTITIES
    }
    checks["technical_terms_preserved"] = all(
        counts["before"] == counts["after"] for counts in entity_counts.values()
    )
    if not all(checks.values()):
        raise AssertionError(f"Verification failed for {raw['url']}: {checks}")
    report = {
        "url": raw["url"], "markdown_characters_before": len(raw["markdown"]),
        "markdown_characters_after": len(cleaned.markdown),
        "headings": len(_headings(after)), "code_blocks": len(_code_source(cleaned.markdown, after)),
        "meaningful_links": sum(count for (kind, _), count in _links(after).items() if kind == "link"),
        "images": sum(count for (kind, _), count in _links(after).items() if kind == "image"),
        "entities": entity_counts, "checks": checks,
        "entity_count_basis": "Visible Markdown content and code, excluding link destinations",
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/cleaned"))
    args = parser.parse_args()
    paths = args.inputs or sorted(Path("output").glob("page*.json"))
    if not paths:
        parser.error("No crawler page JSON files found.")
    for path in paths:
        if path.resolve() == (args.output_dir / path.name).resolve():
            parser.error("The output directory must differ from the raw crawl directory.")
    reports = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        output, report = verify_document(raw)
        (args.output_dir / path.name).write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        reports.append(report)
        print(f"PASS {path.name}: {report['headings']} headings, "
              f"{report['code_blocks']} code blocks, {report['meaningful_links']} links")
    (args.output_dir / "verification.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
