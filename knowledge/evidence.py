"""Recover evidence offsets while preserving the original Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

from markdown_it import MarkdownIt
from markdown_it.token import Token

_MARKDOWN = MarkdownIt("commonmark", {"html": True})
_LINK_END = re.compile(r"\]\([^()\s]+\)")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int
    text: str
    kind: Literal["exact", "markdown", "whitespace"]


@dataclass(frozen=True)
class EvidenceMatch:
    span: EvidenceSpan
    prose: str
    complete: bool


def _project(raw: str, tokens: list[Token]) -> tuple[str, list[int], list[int], set[int]] | None:
    """Align parsed inline tokens with raw characters, skipping only verified markup."""
    visible = []
    starts, ends = [], []
    protected = set()
    scopes = []
    opening = None
    cursor = 0
    for token in tokens:
        kind = token.type
        if kind in {"em_open", "strong_open", "link_open"}:
            marker = "[" if kind == "link_open" else token.markup
            if not raw.startswith(marker, cursor):
                return None
            if opening is None:
                opening = cursor
            scopes.append(len(starts))
            cursor += len(marker)
            continue
        if kind in {"em_close", "strong_close", "link_close"}:
            link = _LINK_END.match(raw, cursor) if kind == "link_close" else None
            marker = link.group() if link else token.markup
            if not marker or not raw.startswith(marker, cursor) or not scopes or not ends:
                return None
            cursor += len(marker)
            ends[-1] = cursor
            # Avoid splitting a sentence in the middle of a formatting scope.
            protected.update(range(scopes.pop(), len(starts) - 1))
            continue

        if kind == "code_inline":
            marker = token.markup
            closing = re.compile(r"(?<!`)" + re.escape(marker) + r"(?!`)").search(
                raw, cursor + len(marker),
            )
            if not raw.startswith(marker, cursor) or closing is None:
                return None
            part = raw[cursor:closing.end()]
            protected.update(range(len(starts), len(starts) + len(part)))
        elif kind in {"text", "softbreak"}:
            newline = re.match(r"\r\n?|\n", raw[cursor:]) if kind == "softbreak" else None
            if kind == "softbreak" and newline is None:
                return None
            part = newline.group() if newline else token.content
            if not raw.startswith(part, cursor):
                return None
        else:
            # Escapes, entities, HTML, images and other syntax must match literally.
            return None

        if part:
            visible.append(part)
            starts.extend(range(cursor, cursor + len(part)))
            ends.extend(range(cursor + 1, cursor + len(part) + 1))
            if opening is not None:
                starts[-len(part)] = opening
                opening = None
            cursor += len(part)

    if cursor != len(raw) or scopes:
        return None
    return "".join(visible), starts, ends, protected


class EvidenceMatcher:
    """Match quotes against one chunk with offsets in its original Markdown."""

    def __init__(self, text: str):
        self.text = text

    @cached_property
    def sentences(self) -> list[EvidenceMatch]:
        line_starts = [
            0, *(match.end() for match in re.finditer(r"\r\n?|\n", self.text)), len(self.text),
        ]
        sentences = []
        tokens = _MARKDOWN.parse(self.text)
        for index, token in enumerate(tokens):
            if (token.type != "inline" or not token.map or not token.content
                    or tokens[index - 1].type != "paragraph_open"):
                continue
            if not token.children:
                continue
            # Only paragraphs may establish a prose assertion. List paragraphs can
            # still supply verified spans for the audit.
            line, end_line = token.map
            begin, limit = line_starts[line], line_starts[end_line]
            raw = token.content
            start = self.text.find(raw, begin, limit)
            if start < 0:
                # CommonMark normalizes line endings before creating inline tokens.
                if token.level != 1:
                    continue
                region = self.text[begin:limit]
                raw = region.strip()
                start = begin + len(region) - len(region.lstrip())
            projected = _project(raw, token.children)
            if projected is None:
                continue
            prose, starts, ends, protected = projected
            boundaries = [
                match.end() for match in _SENTENCE_END.finditer(prose)
                if match.start() not in protected
            ]
            previous = 0
            for end in [*boundaries, len(prose)]:
                fragment = prose[previous:end]
                left = previous + len(fragment) - len(fragment.lstrip())
                right = previous + len(fragment.rstrip())
                previous = end
                if left >= right:
                    continue
                raw_start, raw_end = start + starts[left], start + ends[right - 1]
                span = EvidenceSpan(raw_start, raw_end, self.text[raw_start:raw_end], "exact")
                sentences.append(EvidenceMatch(span, prose[left:right], token.level == 1))
        return sentences

    def find(self, quote: str, *, allow_whitespace: bool = False) -> EvidenceMatch | None:
        if not quote.strip():
            return None
        offset = self.text.find(quote)
        if offset >= 0:
            for match in self.sentences:
                if match.complete and match.span.text == quote:
                    return match

        # A literal occurrence can be clipped from formatting around the entire
        # sentence. Prefer a complete verified prose span over an incomplete hit.
        for match in self.sentences:
            span = match.span
            if match.prose == quote and span.text != quote and (match.complete or offset < 0):
                return EvidenceMatch(
                    EvidenceSpan(span.start, span.end, span.text, "markdown"),
                    match.prose, match.complete,
                )
        if offset >= 0:
            span = EvidenceSpan(offset, offset + len(quote), quote, "exact")
            return EvidenceMatch(span, quote, False)
        if allow_whitespace and "`" not in quote:
            for match in self.sentences:
                span = match.span
                if "`" not in span.text and span.text.split() == quote.split():
                    return EvidenceMatch(
                        EvidenceSpan(span.start, span.end, span.text, "whitespace"),
                        match.prose, match.complete,
                    )
        return None
