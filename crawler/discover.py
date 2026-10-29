"""DOM-based link discovery and lightweight documentation-link ranking."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from .utils import normalize_url, within_documentation_root

EXCLUDED_TOKENS = {"login", "sign-in", "sign_in", "logout", "search", "privacy", "terms", "cookie", "advert", "sponsor", "release-notes", "changelog", "blog"}
CONTENT_TOKENS = {"docs", "doc", "guide", "tutorial", "reference", "api", "learn", "manual", "concept", "how-to", "getting-started"}


def _link_score(anchor: Tag) -> int:
    """Rank links using generic semantic DOM signals, not site-specific selectors."""
    href = (anchor.get("href") or "").lower()
    label = anchor.get_text(" ", strip=True).lower()
    context = " ".join(anchor.parent.get("class", []) if anchor.parent else []).lower()
    value = f"{href} {label} {context}"
    if any(token in value for token in EXCLUDED_TOKENS):
        return -10
    return sum(token in value for token in CONTENT_TOKENS) + (1 if len(label) > 2 else 0)


def discover_links(html: str, page_url: str, start_url: str) -> list[str]:
    """Extract, normalize, and prioritize same-site documentation links."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        normalized = normalize_url(href, page_url)
        if within_documentation_root(normalized, start_url):
            score = _link_score(anchor)
            if score >= 0:
                candidates.append((score, normalized))
    # Preserve score order and eliminate duplicates without relying on unordered sets.
    seen: set[str] = set()
    return [url for _, url in sorted(candidates, key=lambda item: -item[0]) if not (url in seen or seen.add(url))]
