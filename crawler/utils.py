"""URL, text, and language helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Return a stable crawl URL without fragments or tracking query parameters."""
    absolute = urljoin(base_url, url) if base_url else url
    parts = urlsplit(absolute)
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    # Keep meaningful query parameters but discard tracking parameters deterministically.
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
               if k.lower() not in TRACKING_QUERY_KEYS and not k.lower().startswith("utm_"))
    )
    return urlunsplit((scheme, host, path, query, ""))


def same_site(url: str, start_url: str) -> bool:
    """Whether a URL is HTTP(S) and belongs to the starting host."""
    candidate, start = urlsplit(url), urlsplit(start_url)
    return candidate.scheme in {"http", "https"} and candidate.netloc.lower() == start.netloc.lower()


def documentation_root(start_url: str) -> str:
    """Infer a broad documentation root from the URL's first semantic segment.

    A site hosted at its domain root remains unrestricted.  Hosts that place docs
    below a conventional documentation segment (for example ``/docs/``) stay in
    that subtree, preventing a crawl from spilling into marketing pages.
    """
    path = urlsplit(start_url).path
    segments = [segment for segment in path.split("/") if segment]
    if segments and segments[0].lower() in CONTENT_ROOT_SEGMENTS:
        return f"/{segments[0]}/"
    return "/"


CONTENT_ROOT_SEGMENTS = {"docs", "documentation", "learn", "guide", "guides", "api", "reference", "manual"}


def within_documentation_root(url: str, start_url: str) -> bool:
    """Check that a same-host URL stays within the inferred documentation area."""
    if not same_site(url, start_url):
        return False
    root = documentation_root(start_url)
    return root == "/" or urlsplit(url).path.startswith(root)


def text_hash(text: str) -> str:
    """Compute a SHA-256 content fingerprint."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collapse_text(text: str) -> str:
    """Normalize prose whitespace while retaining paragraph boundaries."""
    paragraphs = (re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n", text))
    return "\n\n".join(p for p in paragraphs if p)


def detect_language(text: str, html_lang: str | None = None) -> str:
    """Use the HTML language declaration, with a conservative English fallback."""
    if html_lang:
        return html_lang.split("-", 1)[0].lower()
    ascii_letters = sum(char.isascii() and char.isalpha() for char in text)
    letters = sum(char.isalpha() for char in text)
    return "en" if letters and ascii_letters / letters > 0.8 else "unknown"
