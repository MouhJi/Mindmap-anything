from crawler.cleaner import clean_markdown
from crawler.discover import discover_links
from crawler.utils import normalize_url


def test_normalize_url_removes_fragment_tracking_and_duplicate_slashes() -> None:
    assert normalize_url("https://example.com/docs//intro/?utm_source=x&ref=a#heading") == "https://example.com/docs/intro/"


def test_discovery_keeps_same_site_content_links_only() -> None:
    html = '''<a href="/docs/guide">Guide</a><a href="/blog/post">Blog</a><a href="https://other.example/docs">Other</a>'''
    assert discover_links(html, "https://example.com/docs/", "https://example.com/docs/") == ["https://example.com/docs/guide"]


def test_markdown_cleanup_preserves_code() -> None:
    assert clean_markdown("# A\n# A\n\n\n```python\n\nprint(1)\n```") == "# A\n\n```python\n\nprint(1)\n```"
