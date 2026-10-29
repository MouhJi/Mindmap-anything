"""Crawl4AI adapter isolated from pipeline and content logic."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .models import CrawlerConfig

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RenderedPage:
    """The small crawler-agnostic representation consumed by the pipeline."""

    url: str
    html: str


class Crawl4AIRenderer:
    """Render a URL through Crawl4AI and retry transient failures."""

    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config
        self._crawler = None

    async def __aenter__(self) -> "Crawl4AIRenderer":
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
        except ImportError as error:
            raise RuntimeError("Install crawl4ai and Playwright before crawling.") from error
        browser_config = BrowserConfig(headless=True, verbose=False, user_agent=self.config.user_agent)
        self._crawler = AsyncWebCrawler(config=browser_config)
        self._run_config = CrawlerRunConfig(
            wait_until="networkidle", page_timeout=self.config.timeout * 1000
        )
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._crawler:
            await self._crawler.__aexit__(*args)

    async def fetch(self, url: str) -> RenderedPage:
        """Render one page, retrying failures with short exponential backoff."""
        assert self._crawler is not None
        last_error: Exception | None = None
        for attempt in range(self.config.retry + 1):
            try:
                # Wait for network idle when supported by Crawl4AI's current API.
                result = await asyncio.wait_for(
                    self._crawler.arun(url=url, config=self._run_config), timeout=self.config.timeout + 2
                )
                if not getattr(result, "success", True):
                    raise RuntimeError(getattr(result, "error_message", "Crawl4AI returned failure"))
                html = getattr(result, "html", "") or getattr(result, "cleaned_html", "")
                if not html:
                    raise RuntimeError("Rendered page contained no HTML")
                return RenderedPage(url=getattr(result, "url", url) or url, html=html)
            except Exception as error:  # Error is logged by the orchestrator and does not abort crawl.
                last_error = error
                if attempt < self.config.retry:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Could not fetch {url}: {last_error}")
