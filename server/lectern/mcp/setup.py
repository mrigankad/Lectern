"""How to connect each agent client to Lectern's MCP server. Served at GET /api/mcp/setup and quoted in README."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["mcp"])


def server_dir() -> Path:
    """The `server/` folder: the uv project the stdio command runs in."""
    return Path(__file__).resolve().parents[2]


def http_url() -> str:
    return os.environ.get("LECTERN_MCP_URL", "http://localhost:8000/mcp")


def setup(directory: str | None = None, url: str | None = None) -> dict[str, Any]:
    """Copy-paste setup for every supported client, filled in with this machine's paths."""
    folder = (directory or str(server_dir())).replace("\\", "/")
    url = url or http_url()
    args = ["--directory", folder, "run", "lectern-mcp"]
    stdio = {"command": "uv", "args": args}
    stdio_json = json.dumps({"mcpServers": {"lectern": stdio}}, indent=2)
    http_json = json.dumps({"mcpServers": {"lectern": {"url": url}}}, indent=2)
    clients = [
        {"id": "claude_code", "name": "Claude Code", "where": "In your terminal", "format": "shell",
         "file": None,
         "stdio": f'claude mcp add lectern -- uv --directory "{folder}" run lectern-mcp',
         "http": f"claude mcp add --transport http lectern {url}"},
        {"id": "claude_desktop", "name": "Claude desktop", "where": "In a chat", "format": "json",
         "file": "claude_desktop_config.json (Settings > Developer > Edit config)",
         "stdio": stdio_json,
         "http": None},
        {"id": "codex", "name": "Codex", "where": "Coding agent", "format": "toml",
         "file": "~/.codex/config.toml",
         "stdio": f'[mcp_servers.lectern]\ncommand = "uv"\nargs = {json.dumps(args)}\n',
         "http": f'[mcp_servers.lectern]\nurl = "{url}"\n'},
        {"id": "cursor", "name": "Cursor", "where": "In your editor", "format": "json",
         "file": ".cursor/mcp.json (this project) or ~/.cursor/mcp.json",
         "stdio": stdio_json, "http": http_json},
        {"id": "gemini_cli", "name": "Gemini CLI", "where": "In your terminal", "format": "json",
         "file": "~/.gemini/settings.json",
         "stdio": stdio_json,
         "http": json.dumps({"mcpServers": {"lectern": {"httpUrl": url}}}, indent=2)},
        {"id": "antigravity", "name": "Antigravity", "where": "Agent workspace", "format": "json",
         "file": "mcp_config.json (Agent panel > MCP servers > Manage > View raw config)",
         "stdio": stdio_json,
         "http": json.dumps({"mcpServers": {"lectern": {"serverUrl": url}}}, indent=2)},
    ]
    return {
        "name": "lectern",
        "stdio": {**stdio, "note": "Starts Lectern inside the agent. Needs uv. Works without the web app running."},
        "http": {"url": url, "note": "Uses the running Lectern server, so the web app shows the build live."},
        "clients": clients,
    }


@router.get("/mcp/setup")
async def get_setup() -> dict[str, Any]:
    return setup()
