"""Models for the corpus"""

import hashlib

from pydantic import BaseModel, ConfigDict


class RawPage(BaseModel):
    """A fetched Mardown page"""

    model_config = ConfigDict(frozen=True)

    page_id: str
    canonical_url: str
    content_markdown: str
    source_hash: str

    @classmethod
    def from_markdown(cls, page_id: str, canonical_url: str, content_markdown: str) -> "RawPage":
        """Create a RawPage from Markdown content and compute its source hash."""
        return cls(
            page_id=page_id,
            canonical_url=canonical_url,
            content_markdown=content_markdown,
            source_hash=hashlib.sha256(content_markdown.encode()).hexdigest(),
        )


class DocChunk(BaseModel):
    """Model for the immutable document chunks"""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    page_id: str
    title: str
    heading_path: tuple[str, ...]
    content_markdown: str
    canonical_url: str
    local_ordinal: int
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
