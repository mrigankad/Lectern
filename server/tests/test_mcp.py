"""The MCP server: every tool through an in-process MCP client, plus the HTTP mount and the setup endpoint."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from mcp import Client

from lectern.mcp.server import build_server

from .conftest import BOARD_PROMPT

TOOLS = {"create_deck", "get_outline", "update_outline", "regenerate_outline", "approve_outline", "get_status",
         "wait_until_ready", "get_interview", "answer_interview", "skip_interview", "get_critic_report", "fix_findings", "ask", "edit_slide", "list_decks", "export_deck"}


async def call(c: Client, name: str, **args: Any) -> dict[str, Any]:
    result = await c.call_tool(name, args)
    assert not result.is_error, result.content
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    assert isinstance(data, dict), result
    return data


async def error_of(c: Client, name: str, **args: Any) -> str:
    result = await c.call_tool(name, args)
    assert result.is_error
    return result.content[0].text  # type: ignore[union-attr]


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_full_flow_through_mcp(client: TestClient, data_dir: Path) -> None:
    source = data_dir / "notes.md"
    source.write_text("Net revenue retention fell from 112% to 104%.", encoding="utf-8")

    async def flow() -> None:
        async with Client(build_server()) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert TOOLS <= names
            approve = next(t for t in (await c.list_tools()).tools if t.name == "approve_outline")
            assert "ONLY after the" in (approve.description or "")

            outline = await call(c, "create_deck", prompt=BOARD_PROMPT, audience="the board", minutes=10,
                                 source_paths=[str(source)])
            deck_id = outline["deck_id"]
            assert outline["status"] == "outline_ready" and outline["slides"]
            assert outline["web_url"].endswith(f"/decks/{deck_id}/outline")
            assert "approve" in outline["next"]

            again = await call(c, "get_outline", deck_id=deck_id)
            assert again["slides"] == outline["slides"]
            # Not approved: nothing is built.
            assert (await call(c, "get_status", deck_id=deck_id))["progress"]["ready"] == 0

            slides = [{"id": s["id"], "headline": s["headline"], "layout": s["layout"], "section": s["section"]}
                      for s in outline["slides"]][:5]
            slides[1]["headline"] = "Churn is now our biggest risk"
            edited = await call(c, "update_outline", deck_id=deck_id, slides=slides, title="Q3 board review")
            assert edited["title"] == "Q3 board review" and len(edited["slides"]) == 5
            assert edited["slides"][1]["headline"] == "Churn is now our biggest risk"

            redrafted = await call(c, "regenerate_outline", deck_id=deck_id, instruction="make it shorter")
            assert redrafted["status"] == "outline_ready"

            started = await call(c, "approve_outline", deck_id=deck_id)
            assert started["status"] in {"building", "ready"}
            done = await call(c, "wait_until_ready", deck_id=deck_id, timeout_seconds=60)
            assert done["status"] == "ready", done
            assert done["progress"]["ready"] == done["progress"]["total"]
            assert done["activity"] and all("summary" in a for a in done["activity"])

            report = await call(c, "get_critic_report", deck_id=deck_id)
            assert 0 <= report["score"] <= 100 and "findings" in report
            fixed = await call(c, "fix_findings", deck_id=deck_id)
            assert "score" in fixed
            kept = await call(c, "fix_findings", deck_id=deck_id, action="keep")
            assert all(f["status"] != "open" for f in kept["findings"])

            asked = await call(c, "ask", deck_id=deck_id, slide_index=2, message="Make the headline shorter")
            assert asked["status"] in {"done", "failed"} and asked["result"]
            whole = await call(c, "ask", deck_id=deck_id, message="Tighten the speaker notes")
            assert whole["status"] in {"done", "failed"}

            slide = await call(c, "edit_slide", deck_id=deck_id, slide_index=1, headline="Q3: growth with a leak",
                               notes="Open with the ask.")
            assert slide["slide"]["headline"] == "Q3: growth with a leak"
            assert slide["slide"]["notes"] == "Open with the ask."

            listed = await call(c, "list_decks")
            assert [d["id"] for d in listed["decks"]] == [deck_id]

            exported = await call(c, "export_deck", deck_id=deck_id)
            path = Path(exported["path"])
            assert path.is_file() and path.suffix == ".pptx" and path.stat().st_size == exported["bytes"]
            assert data_dir in path.parents
            assert exported["download_url"].endswith(path.parent.name)
            assert exported["report"]["editable_objects"] > 0

            resource = await c.read_resource(f"lectern://decks/{deck_id}")
            deck = json.loads(resource.contents[0].text)  # type: ignore[union-attr]
            assert deck["id"] == deck_id and deck["slides"]
            resource = await c.read_resource(f"lectern://decks/{deck_id}/outline")
            assert json.loads(resource.contents[0].text)["slides"]  # type: ignore[union-attr]

    run(flow())


def test_interview_through_mcp(client: TestClient, data_dir: Path) -> None:
    async def flow() -> None:
        async with Client(build_server()) as c:
            created = await call(c, "create_deck", prompt=BOARD_PROMPT, interview=True)
            deck_id = created["deck_id"]
            assert created["status"] == "interview" and created["web_url"].endswith("/interview")
            state = await call(c, "get_interview", deck_id=deck_id)
            assert state["questions"] and state["current"]
            state = await call(c, "answer_interview", deck_id=deck_id, question_id=state["current"],
                               answer="The board")
            assert state["questions"][0]["answer"] or any(q["answer"] for q in state["questions"])
            await call(c, "skip_interview", deck_id=deck_id)
            done = await call(c, "wait_until_ready", deck_id=deck_id, timeout_seconds=60)
            assert done["status"] == "outline_ready", done

    run(flow())


def test_errors_are_plain(client: TestClient, data_dir: Path) -> None:
    async def flow() -> None:
        async with Client(build_server()) as c:
            assert "does not exist" in await error_of(c, "get_status", deck_id="dk_missing")
            missing = await error_of(c, "create_deck", prompt="A deck", source_paths=[str(data_dir / "nope.md")])
            assert "does not exist" in missing
            binary = data_dir / "deck.pdf"
            binary.write_bytes(b"%PDF")
            assert "text sources" in await error_of(c, "create_deck", prompt="A deck", source_paths=[str(binary)])
            outline = await call(c, "create_deck", prompt=BOARD_PROMPT)
            assert "at least one slide" in await error_of(c, "update_outline", deck_id=outline["deck_id"], slides=[])
            assert "slide 99" in await error_of(c, "edit_slide", deck_id=outline["deck_id"], slide_index=99)

    run(flow())


def test_http_mount_and_setup(client: TestClient) -> None:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "0"}}}
    response = client.post("/mcp", json=init, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "lectern"
    listed = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed.status_code == 200, listed.text
    assert TOOLS <= {t["name"] for t in listed.json()["result"]["tools"]}

    setup = client.get("/api/mcp/setup").json()
    ids = {c["id"] for c in setup["clients"]}
    assert ids == {"claude_code", "claude_desktop", "codex", "cursor", "gemini_cli", "antigravity"}
    claude = next(c for c in setup["clients"] if c["id"] == "claude_code")
    assert claude["stdio"].startswith("claude mcp add lectern -- uv --directory")
    assert claude["http"].endswith("/mcp")
