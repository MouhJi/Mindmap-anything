"""Public document API and bounded, content-free diagnostic logging."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ..models import Document
from .markdown_cleaner import _clean_markdown
from .models import CleanDocument, RawDocument
from .text_cleaner import clean_text

LOGGER = logging.getLogger(__name__)


class DocumentCleaner:
    """Clean crawler models or page JSON mappings without mutating the input."""

    def clean(self, document: Document | Mapping[str, Any]) -> CleanDocument:
        data = document.model_dump() if isinstance(document, Document) else dict(document)
        raw = RawDocument.model_validate(deepcopy(data))
        markdown, stats = _clean_markdown(raw.markdown)
        result = CleanDocument.model_validate({
            **raw.model_dump(), "markdown": markdown, "text": clean_text(raw.text),
        })
        LOGGER.debug(
            "Cleaned document: markdown length %d -> %d; navigation blocks=%d; "
            "heading anchors=%d; duplicate headings=%d; whitespace lines=%d",
            len(raw.markdown), len(markdown), stats.navigation_blocks,
            stats.heading_anchors, stats.duplicate_headings, stats.whitespace_lines,
        )
        return result


def clean_document(document: Document | Mapping[str, Any]) -> CleanDocument:
    """Convenience wrapper around DocumentCleaner.clean()."""
    return DocumentCleaner().clean(document)
