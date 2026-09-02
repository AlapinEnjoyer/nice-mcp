"""Frozen MCP tool registration."""

from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from nice_mcp.contracts import (
    GET_DOC_CHUNKS_DESCRIPTION,
    SEARCH_DOCS_DESCRIPTION,
    GetDocChunksInput,
    GetDocChunksOutput,
    SearchDocsInput,
    SearchDocsOutput,
)
from nice_mcp.server.runtime import CorpusService


def register_tools(server: MCPServer, service: CorpusService) -> None:
    """Register exactly the two model-facing retrieval tools."""

    @server.tool(name="search_docs", description=SEARCH_DOCS_DESCRIPTION, structured_output=True)
    def search_docs(
        query: Annotated[str, Field(min_length=1, max_length=1000)],
        limit: Annotated[int, Field(ge=1, le=10)] = 5,
    ) -> SearchDocsOutput:
        """Search official NiceGUI documentation."""
        request = SearchDocsInput(query=query, limit=limit)
        return service.search(request.query, request.limit)

    @server.tool(name="get_doc_chunks", description=GET_DOC_CHUNKS_DESCRIPTION, structured_output=True)
    def get_doc_chunks(
        chunk_ids: Annotated[list[str], Field(min_length=1, max_length=4)],
    ) -> GetDocChunksOutput:
        """Fetch authoritative Markdown by stable chunk ID."""
        request = GetDocChunksInput(chunk_ids=chunk_ids)
        return service.get_chunks(request.chunk_ids)
