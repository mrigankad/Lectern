"""Lectern as an MCP server: stdio (`uv run lectern-mcp`) and streamable HTTP mounted on the API at /mcp."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from .server import build_server


def mount(app: FastAPI) -> Any:
    """Add POST/GET /mcp to the app. Returns the session manager; run it in the app's lifespan."""
    server = build_server()
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", "testserver"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )
    sub = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                     transport_security=security)
    for route in sub.routes:
        app.router.add_route(route.path, route.endpoint, include_in_schema=False)  # type: ignore[attr-defined]
    return server.session_manager


def main() -> None:
    """Console script `lectern-mcp`: the stdio server, sharing Lectern's database."""
    import anyio

    from ..agents.pipeline import pipeline
    from ..db import init_db
    from ..llm import router as llm
    from ..media import router as media_router

    async def run() -> None:
        init_db()
        llm.seed_defaults()
        media_router.seed_defaults()
        # No recover() here: the web server may be building decks in this same database right now.
        try:
            await build_server().run_stdio_async()
        finally:
            await pipeline.shutdown()

    anyio.run(run)
