"""Internal retrieval interfaces and shared document representation."""

from dataclasses import dataclass
from typing import Protocol

from nice_mcp.corpus.models import DocChunk


@dataclass(frozen=True)
class RankedChunk:
    """An internal ranked result; scores never cross the MCP boundary."""

    chunk_id: str
    score: float


class Retriever(Protocol):
    """Common interface implemented by every retrieval strategy."""

    def search(self, query: str, limit: int) -> list[RankedChunk]:
        """Return ranked independently resolvable chunk IDs."""
        ...


def searchable_text(chunk: DocChunk) -> str:
    """Create the shared retrieval document representation."""
    headings = " > ".join(chunk.heading_path)
    return f"{headings}\n{chunk.content_markdown}".strip()
