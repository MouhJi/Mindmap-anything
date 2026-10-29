"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .models import CrawlerConfig
from .pipeline import DocumentationCrawler


def main() -> None:
    """Parse arguments and execute the crawl."""
    parser = argparse.ArgumentParser(description="Crawl and clean a documentation site.")
    parser.add_argument("url", help="Single documentation URL to crawl")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retry", type=int, default=2)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = CrawlerConfig(**vars(args))
    documents = asyncio.run(DocumentationCrawler(config).crawl(args.url))
    print(f"Saved {len(documents)} unique pages to {config.output_dir}")


if __name__ == "__main__":
    main()
