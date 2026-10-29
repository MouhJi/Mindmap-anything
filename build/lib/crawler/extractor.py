"""Extract article-like documentation content from rendered HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify


NOISE_TAGS = {"nav", "footer", "aside", "form", "dialog", "script", "style", "noscript", "svg"}
NOISE_WORDS = {"navigation", "sidebar", "footer", "cookie", "banner", "advert", "menu", "search"}


def _is_noise(element: Tag) -> bool:
    attrs = " ".join(element.get("class", [])) + " " + str(element.get("id", ""))
    return element.name in NOISE_TAGS or any(word in attrs.lower() for word in NOISE_WORDS)


def _best_content_root(soup: BeautifulSoup) -> Tag:
    """Choose the largest semantic/article-like region from the rendered page."""
    roots = soup.select("main, article, [role='main']") or soup.find_all(["section", "div"])
    if not roots:
        return soup.body or soup
    return max(roots, key=lambda node: len(node.get_text(" ", strip=True)))


def extract_page(html: str) -> tuple[str, str, str, str | None]:
    """Return title, clean Markdown, plain text, and declared page language."""
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(" ", strip=True) if soup.title else "")
    root = _best_content_root(soup)
    for element in list(root.find_all(True)):
        # A parent removed earlier in the loop leaves its descendants decomposed.
        if not element.name:
            continue
        if _is_noise(element):
            element.decompose()
    markdown = markdownify(str(root), heading_style="ATX", bullets="-").strip()
    text = root.get_text("\n", strip=True)
    html_tag = soup.find("html")
    language = html_tag.get("lang") if html_tag else None
    return title, markdown, text, language
