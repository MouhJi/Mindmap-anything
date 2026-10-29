"""Small generic UI vocabulary, matched against whole blocks only."""

import re

from markdown_it import MarkdownIt

UI_LABELS = frozenset({
    "back to top", "previous", "next", "edit this page", "share",
    "copy page", "table of contents",
})


def is_navigation_block(lines: list[str], parser: MarkdownIt | None = None) -> bool:
    """Require every line to be an exact UI label or a single labelled link.

    No substring matching, URL/domain heuristics, or removal of links whose
    labels contain substantive documentation titles. Markdown callers only
    apply this to top-level paragraphs, never lists, headings, or quotations.
    """
    if not lines:
        return False
    for line in lines:
        label = line.strip()
        if parser is not None:
            tokens = parser.parseInline(label)[0].children or []
            if [token.type for token in tokens] == ["link_open", "text", "link_close"]:
                label = tokens[1].content
        if re.sub(r"[ \t]+", " ", label).casefold() not in UI_LABELS:
            return False
    return True
