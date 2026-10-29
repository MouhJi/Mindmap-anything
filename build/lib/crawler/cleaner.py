"""Backward-compatible entry points for the crawler's cleaning stage."""

from .cleaning import clean_markdown, clean_text

__all__ = ["clean_markdown", "clean_text"]
