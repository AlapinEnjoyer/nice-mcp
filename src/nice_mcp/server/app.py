"""MCP server construction and Streamable HTTP application."""

from mcp.server import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from nice_mcp.server.runtime import CorpusService
from nice_mcp.server.tools import register_tools


def create_mcp_server(service: CorpusService) -> MCPServer:
    """Create a transport-neutral stateless MCP server."""
    server = MCPServer(
        name="nice-mcp",
        title="NiceGUI Documentation",
        description="Unofficial retrieval server for NiceGUI documentation.",
        version="0.1.0",
    )
    register_tools(server, service)
    return server


def create_http_app(service: CorpusService) -> Starlette:
    """Create the Streamable HTTP application."""
    server = create_mcp_server(service)

    @server.custom_route("/health/live", methods=["GET"])
    async def live(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @server.custom_route("/health/ready", methods=["GET"])
    async def ready(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ready", "corpus_revision": service.manifest.corpus_revision})

    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        max_request_body_size=64 * 1024,
    )
