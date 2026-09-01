"""Canonical NiceGUI documentation page discovery."""

from urllib.parse import urldefrag, urljoin, urlparse

from pydantic import BaseModel


class SearchIndexEntry(BaseModel):
    """One entry from NiceGUI's flat documentation search index."""

    title: str
    content: str
    format: str
    url: str


def discover_page_urls(
    entries: list[SearchIndexEntry],
    *,
    base_url: str = "https://nicegui.io",
) -> list[str]:
    """Extract unique canonical documentation page URLs."""
    discovered: set[str] = set()

    for entry in entries:
        raw_url = entry.url
        absolute = urljoin(base_url, raw_url)
        clean, _ = urldefrag(absolute)
        parsed = urlparse(clean)
        if parsed.scheme == "https" and parsed.netloc == "nicegui.io" and parsed.path.startswith("/documentation"):
            discovered.add(clean.rstrip("/"))
    return sorted(discovered)


def page_id_from_url(url: str) -> str:
    """Derive a logical page identifier from a documentation URL."""
    path = urlparse(url).path.strip("/")
    suffix = path.removeprefix("documentation/")

    return suffix.replace("/", "-") or "documentation"
