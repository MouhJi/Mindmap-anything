"""Conservative cleanup of the crawler's secondary text representation."""

import re

from ..utils import collapse_text
from .noise import is_navigation_block


def clean_text(text: str) -> str:
    """Normalize paragraphs without reconstructing Markdown from plain text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n(?:[ \t]*\n)+", text)
    # Plain text has no structure to distinguish UI words from code or prose.
    # Only remove complete blocks, never matching individual words in prose.
    return collapse_text("\n\n".join(
        block for block in blocks if not is_navigation_block(block.splitlines())
    )).strip()
