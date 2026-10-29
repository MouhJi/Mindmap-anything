"""Edit Markdown source spans without rendering or rewriting protected content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from markdown_it import MarkdownIt

from .noise import is_navigation_block


@dataclass(frozen=True)
class Heading:
    """A heading's level, inline Markdown, and one-based source line."""

    level: int
    title: str
    line: int


@dataclass
class CleaningStats:
    navigation_blocks: int = 0
    heading_anchors: int = 0
    duplicate_headings: int = 0
    whitespace_lines: int = 0


def _parser() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": True})


class _HTMLContext(HTMLParser):
    """Track wrappers across CommonMark HTML blocks separated by blank lines."""

    VOID_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in self.VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.stack:
            last = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[last:]


def _without_anchor(line: str, parser: MarkdownIt) -> str:
    # Let the parser validate link syntax (balanced URLs and optional titles).
    # Optional ATX closing hashes remain part of the original heading syntax.
    closing = re.search(r"[ \t]+#+[ \t]*$", line)
    suffix = closing.group() if closing else ""
    body = line[:closing.start()] if closing else line
    for match in re.finditer(r"(?<!\\)\[¶\]\(", body):
        children = parser.parseInline(body[match.start():].rstrip())[0].children or []
        if ([token.type for token in children] == ["link_open", "text", "link_close"]
                and children[1].content == "¶"):
            return body[:match.start()].rstrip() + suffix
    return line


def _clean_markdown(markdown: str) -> tuple[str, CleaningStats]:
    parser = _parser()
    tokens = parser.parse(markdown)
    # Keep original line terminators inside protected spans, including CRLF.
    lines = re.findall(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", markdown)
    protected: set[int] = set()
    code: set[int] = set()
    html_starts: set[int] = set()
    removed: set[int] = set()
    headings: set[int] = set()
    stats = CleaningStats()

    for token in tokens:
        if token.map is None:
            continue
        start, end = token.map
        if token.type in {"fence", "code_block", "html_block"}:
            protected.update(range(start, end))
            if token.type == "html_block":
                html_starts.add(start)
            else:
                code.update(range(start, end))
        elif token.type == "inline" and any(
            child.type in {"code_inline", "html_inline"} for child in token.children or []
        ) and end - start > 1:
            # Multiline inline code/HTML can carry meaningful whitespace too.
            protected.update(range(start, end))
        elif token.type == "heading_open":
            headings.add(end - 2 if token.markup in {"=", "-"} else start)
        elif token.type == "paragraph_open" and token.level == 0:
            if is_navigation_block(lines[start:end], parser):
                removed.update(range(start, end))
                stats.navigation_blocks += 1

    html_context = _HTMLContext()
    for index, raw in enumerate(lines):
        if index in code:
            continue
        if index in html_starts or html_context.stack:
            protected.add(index)
            html_context.feed(raw)
    # A paragraph inside a raw HTML wrapper is semantic content, even if its
    # text happens to equal a UI label. Count only removals actually applied.
    stats.navigation_blocks = sum(
        token.type == "paragraph_open" and token.level == 0 and token.map is not None
        and token.map[0] in removed and not any(
            index in protected for index in range(*token.map)
        )
        for token in tokens
    )

    result: list[tuple[str, bool]] = []
    previous_heading: str | None = None
    for index, raw in enumerate(lines):
        if index in protected:
            result.append((raw, True))
            previous_heading = None
            continue
        if index in removed:
            continue
        line = raw.rstrip("\r\n")
        if index in headings:
            cleaned = _without_anchor(line, parser)
            stats.heading_anchors += cleaned != line
            line = cleaned
        # Two trailing spaces express a Markdown hard break. Preserve that
        # meaning, indentation, and all internal whitespace (tables/inline code).
        trimmed = line.rstrip(" \t")
        if trimmed and line.endswith("  "):
            trimmed += "  "
        normalized = trimmed + ("\n" if raw.endswith(("\r", "\n")) else "")
        stats.whitespace_lines += normalized != raw
        # Only immediately adjacent identical ATX headings are unambiguous
        # crawler duplicates. Never deduplicate prose, lists, code or sections.
        if index in headings and line.lstrip().startswith("#"):
            if previous_heading == trimmed:
                stats.duplicate_headings += 1
                continue
            previous_heading = trimmed
        else:
            previous_heading = None
        if not trimmed:
            if not result or (not result[-1][1] and not result[-1][0].strip()):
                continue
            normalized = "\n"
        result.append((normalized, False))

    while result and not result[-1][1] and not result[-1][0].strip():
        result.pop()
    if result and not result[-1][1]:
        result[-1] = (result[-1][0].removesuffix("\n"), False)
    return "".join(line for line, _ in result), stats


def clean_markdown(markdown: str) -> str:
    """Light cleaning, preserving code/HTML verbatim and Markdown semantics."""
    return _clean_markdown(markdown)[0]


def extract_headings(markdown: str) -> list[Heading]:
    """Expose section locations without chunking or modifying metadata."""
    tokens = _parser().parse(markdown)
    return [
        Heading(level=int(token.tag[1:]), title=tokens[index + 1].content,
                line=token.map[0] + 1)
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.map is not None
    ]
