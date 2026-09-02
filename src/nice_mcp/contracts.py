"""Frozen model-facing MCP contract."""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

SEARCH_DOCS_DESCRIPTION = (
    "Search the official NiceGUI documentation for APIs, concepts, examples, and development patterns. "
    "Returns ranked documentation chunks with short excerpts and stable chunk IDs. Use this before answering "
    "NiceGUI-specific questions when the relevant API or behavior is uncertain. Fetch full content with "
    "get_doc_chunks when an excerpt is insufficient."
)
GET_DOC_CHUNKS_DESCRIPTION = (
    "Fetch the full Markdown for specific NiceGUI documentation chunk IDs returned by search_docs. "
    "Use this when complete explanation, code examples, or neighboring context is needed. Chunk IDs are independent "
    "of MCP sessions and may be fetched in a later request."
)
CHUNK_ID_PATTERN = re.compile(r"^ngc_[0-9a-f]{12}$")  # nicegui chunk


class ContractModel(BaseModel):
    """Strict base model for public request and response values."""

    model_config = ConfigDict(extra="forbid", strict=True)


class SearchDocsInput(ContractModel):
    """Input to ``search_docs``."""

    query: Annotated[str, Field(min_length=1, max_length=1000)]
    limit: Annotated[int, Field(ge=1, le=10)] = 5

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only queries while preserving caller text."""
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


class GetDocChunksInput(ContractModel):
    """Input to ``get_doc_chunks``."""

    chunk_ids: Annotated[list[str], Field(min_length=1, max_length=4)]

    @field_validator("chunk_ids")
    @classmethod
    def validate_chunk_ids(cls, values: list[str]) -> list[str]:
        """Require unique stable NiceGUI chunk identifiers."""
        if len(values) != len(set(values)):
            raise ValueError("chunk_ids must be unique")
        if invalid := [value for value in values if not CHUNK_ID_PATTERN.fullmatch(value)]:
            raise ValueError(f"invalid chunk IDs: {invalid}")
        return values


class BaseChunkOutput(ContractModel):
    """Common fields shared by all chunk output shapes."""

    chunk_id: str
    page_id: str
    title: str
    heading_path: list[str]
    canonical_url: str


class SearchResult(BaseChunkOutput):
    """A ranked documentation discovery object."""

    excerpt: str
    previous_chunk_id: str | None
    next_chunk_id: str | None


class SearchDocsOutput(ContractModel):
    """Output from ``search_docs``."""

    query: str
    corpus_revision: str
    results: list[SearchResult]


class DocChunkOutput(BaseChunkOutput):
    """Full authoritative Markdown for a chunk."""

    content_markdown: str


class GetDocChunksOutput(ContractModel):
    """Output from ``get_doc_chunks`` with partial-success semantics."""

    corpus_revision: str
    chunks: list[DocChunkOutput]
    missing_chunk_ids: list[str]
