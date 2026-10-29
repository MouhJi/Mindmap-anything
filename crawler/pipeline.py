"""Concurrent BFS documentation crawling orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import aiofiles

from .cleaner import clean_markdown, clean_text
from .crawler import Crawl4AIRenderer
from .deduplicator import Deduplicator
from .discover import discover_links
from .extractor import extract_page
from .models import CrawlIndex, CrawlItem, CrawlerConfig, Document, DocumentMetadata
from .utils import detect_language, normalize_url

LOGGER = logging.getLogger(__name__)


class DocumentationCrawler:
    """A reusable async BFS crawler that produces documentation documents only."""

    def __init__(self, config: CrawlerConfig, renderer: Crawl4AIRenderer | None = None) -> None:
        self.config = config
        self.renderer = renderer or Crawl4AIRenderer(config)
        self.errors: list[str] = []
        self.skipped = 0
        self._deduplicator = Deduplicator()

    async def crawl(self, start_url: str) -> list[Document]:
        """Crawl from one URL, save page JSON files and return unique documents."""
        started = monotonic()
        start_url = normalize_url(start_url)
        queue: list[CrawlItem] = [CrawlItem(url=start_url, depth=0)]
        visited: set[str] = set()
        documents: list[Document] = []
        await asyncio.to_thread(self.config.output_dir.mkdir, parents=True, exist_ok=True)

        async with self.renderer:
            while queue and len(documents) < self.config.max_pages:
                slots = min(len(queue), self.config.concurrency, self.config.max_pages - len(documents))
                level = [queue.pop(0) for _ in range(slots)]
                accepted: list[CrawlItem] = []
                for item in level:
                    if item.url not in visited:
                        visited.add(item.url)
                        accepted.append(item)
                results = await asyncio.gather(*(self._process(item, start_url) for item in accepted), return_exceptions=True)
                for item, result in zip(accepted, results):
                    if isinstance(result, Exception):
                        self.errors.append(str(result))
                        LOGGER.warning("Failed %s: %s", item.url, result)
                        continue
                    document, links = result
                    if document is not None:
                        documents.append(document)
                        await self._write_document(document, len(documents))
                    if item.depth < self.config.max_depth:
                        queue.extend(CrawlItem(url=link, depth=item.depth + 1, parent=item.url)
                                     for link in links if link not in visited)
                    if len(documents) >= self.config.max_pages:
                        break
        await self._write_index(start_url, documents, started)
        return documents

    async def _process(self, item: CrawlItem, start_url: str) -> tuple[Document | None, list[str]]:
        page = await self.renderer.fetch(item.url)
        normalized = normalize_url(page.url)
        title, markdown, text, language = extract_page(page.html)
        markdown, text = clean_markdown(markdown), clean_text(text)
        links = discover_links(page.html, normalized, start_url)
        if not text or len(text) < 40:
            self.skipped += 1
            LOGGER.info("Skipping empty page %s", normalized)
            return None, links
        is_new, digest = self._deduplicator.add_if_new(text)
        if not is_new:
            self.skipped += 1
            LOGGER.info("Skipping duplicate page %s", normalized)
            return None, links
        document = Document(
            url=normalized, title=title or normalized, markdown=markdown, text=text,
            metadata=DocumentMetadata(depth=item.depth, parent=item.parent,
                domain=urlsplit(normalized).netloc, crawl_time=datetime.now(timezone.utc),
                language=detect_language(text, language), hash=digest,
                original_url=item.url, normalized_url=normalized),
        )
        return document, links

    async def _write_document(self, document: Document, number: int) -> None:
        path = self.config.output_dir / f"page{number:04d}.json"
        async with aiofiles.open(path, "w", encoding="utf-8") as file:
            await file.write(document.model_dump_json(indent=2))

    async def _write_index(self, start_url: str, documents: list[Document], started: float) -> None:
        index = CrawlIndex(start_url=start_url, total_pages=len(documents),
            crawl_duration_seconds=round(monotonic() - started, 3), skipped_pages=self.skipped,
            failed_pages=len(self.errors), generated_at=datetime.now(timezone.utc), errors=self.errors)
        async with aiofiles.open(self.config.output_dir / "index.json", "w", encoding="utf-8") as file:
            await file.write(index.model_dump_json(indent=2))
