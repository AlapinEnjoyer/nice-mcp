"""Offline Markdown ingestion."""

import asyncio

import httpx
from pydantic import TypeAdapter

from nice_mcp.corpus.discovery import SearchIndexEntry, discover_page_urls, page_id_from_url
from nice_mcp.corpus.models import RawPage

USER_AGENT = "nice-mcp-indexer/0.1 (+https://github.com/AlapinEnjoyer/nice-mcp)"
SEARCH_INDEX_ADAPTER = TypeAdapter(list[SearchIndexEntry])


class IngestionError(RuntimeError):
    """Raise when ingestion of the markdown could not be completed"""


def _validate_markdown(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    body = response.text.replace("\r\n", "\n")
    if "html" in content_type or "<html" in body[:500].lower():
        raise IngestionError(f"expected Markdown, received HTML from {response.url}")
    if len(body.strip()) < 100:
        raise IngestionError(f"unusually small Markdown body from {response.url}")
    return body


async def fetch_corpus(index_url: str, *, concurrency: int = 10) -> list[RawPage]:
    """Discover and fetch the full canonical NiceGUI Markdown corpus."""
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(20.0, connect=10.0)
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers, follow_redirects=True) as client:
        # Load the NiceGUI search index and validate its JSON against our expected schema.
        index_response = await client.get(index_url)
        index_response.raise_for_status()
        entries = SEARCH_INDEX_ADAPTER.validate_python(index_response.json())
        urls = discover_page_urls(entries)
        if not urls:
            raise IngestionError("NiceGUI search index yielded no documentation pages")
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(url: str) -> RawPage:
            page_id = page_id_from_url(url)
            request_headers = {"Accept": "text/markdown", "User-Agent": USER_AGENT}
            async with semaphore:
                response = await client.get(url, headers=request_headers)
                response.raise_for_status()
            content = _validate_markdown(response)
            return RawPage.from_markdown(
                page_id=page_id,
                canonical_url=url,
                content_markdown=content,
            )

        try:
            return list(await asyncio.gather(*(fetch_one(url) for url in urls)))
        except (httpx.HTTPError, ValueError) as error:
            raise IngestionError("NiceGUI corpus ingestion failed") from error
