"""Typed public models used by the crawler."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class CrawlerConfig(BaseModel):
    """Runtime limits for a crawl."""

    max_depth: int = Field(default=5, ge=0)
    max_pages: int = Field(default=500, ge=1)
    concurrency: int = Field(default=5, ge=1, le=20)
    timeout: int = Field(default=30, ge=1, description="Per-page timeout in seconds")
    retry: int = Field(default=2, ge=0, le=5)
    output_dir: Path = Path("output")
    user_agent: str = "UniversalDocsCrawler/0.1 (+https://example.invalid/crawler)"


class DocumentMetadata(BaseModel):
    """Provenance needed by downstream document processors."""

    depth: int
    parent: str | None = None
    domain: str
    crawl_time: datetime
    language: str = "unknown"
    hash: str
    original_url: str
    normalized_url: str


class Document(BaseModel):
    """One cleaned documentation page."""

    url: str
    title: str
    markdown: str
    text: str
    metadata: DocumentMetadata


class CrawlIndex(BaseModel):
    """Summary persisted after a crawl completes."""

    start_url: str
    total_pages: int
    crawl_duration_seconds: float
    skipped_pages: int
    failed_pages: int
    generated_at: datetime
    errors: list[str] = Field(default_factory=list)


class CrawlItem(BaseModel):
    """A queued URL and its traversal provenance."""

    url: str
    depth: int
    parent: str | None = None
