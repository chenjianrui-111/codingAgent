"""Mount the MCP server as a FastAPI sub-application."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_mcp_app():
    """Create the MCP ASGI app for mounting in FastAPI.

    Returns the Starlette/ASGI app produced by FastMCP's
    ``streamable_http_app()`` method, suitable for ``app.mount("/mcp", ...)``.
    """
    from app.mcp.server import create_mcp_server

    mcp_server = create_mcp_server()
    return mcp_server.streamable_http_app()
