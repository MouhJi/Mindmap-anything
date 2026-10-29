"""Content-level duplicate tracking."""

from __future__ import annotations

from .utils import text_hash


class Deduplicator:
    """Stateful SHA-256 duplicate detector."""

    def __init__(self) -> None:
        self._hashes: set[str] = set()

    def add_if_new(self, text: str) -> tuple[bool, str]:
        """Return whether text is new plus its fingerprint."""
        digest = text_hash(text)
        if digest in self._hashes:
            return False, digest
        self._hashes.add(digest)
        return True, digest
