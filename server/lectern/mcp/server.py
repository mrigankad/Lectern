"""Lectern's MCP server: make, review and export decks from Claude Code, Codex, Cursor and other agents.

The tools call the same code the HTTP API uses (the router functions, which work on the store and the
pipeline in this process), so a deck made here is a normal Lectern deck that the web app can open.
"""
from __future__ import annotations

import asyncio
import functools
import json
import os
import time
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from pydantic import Field
from sqlmodel import select

from .. import config, store
from .. import interview as interview_mod
from ..db import session
from ..llm.base import LLMError
from ..models import MessageRow, RunRow
from ..routers import ask as ask_router
from ..routers import critic as critic_router
from ..routers import decks as decks_router
from ..routers import export as export_router
from ..routers import slides as slides_router
from ..schema import (AskIn, DeckCreate, ExportIn, FindingAction, OutlineSlideIn, OutlineUpdate, RegenerateIn,
                      SlidePatch)

INSTRUCTIONS = """\
Lectern makes presentation decks that export as editable PowerPoint files.

Flow: create_deck -> (Lectern drafts an outline) -> show the outline to the user -> update_outline if they want
changes -> approve_outline ONLY after the user has said yes -> wait_until_ready -> get_critic_report /
fix_findings / ask -> export_deck.

The outline is the human checkpoint. Never call approve_outline on your own initiative: show the user the
title and every slide headline first and wait for their go-ahead. Every result includes `web_url`, a link
the user can open to see and edit the deck in the Lectern web app."""

BUSY = {"draft", "building"}
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".html", ".htm", ".xml",
                 ".rst", ".log", ".py", ".ts", ".js"}
SOURCE_LIMIT = 20_000
SOURCES_TOTAL = 60_000
MAX_WAIT = 600

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _plain_errors(fn: F) -> F:
    """Turn Lectern's expected errors into tool errors the model can read and act on."""
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except (store.NotFound, store.Conflict, LLMError) as error:
            raise ToolError(str(error)) from error
    return wrapper  # type: ignore[return-value]


def web_base() -> str:
    return os.environ.get("LECTERN_WEB_URL", "http://localhost:3000").rstrip("/")


def api_base() -> str:
    return os.environ.get("LECTERN_API_URL", "http://localhost:8000").rstrip("/")


def web_url(deck_id: str, status: str) -> str:
    if status == "interview":
        return f"{web_base()}/decks/{deck_id}/interview"
    if status in {"draft", "outline_ready"}:
        return f"{web_base()}/decks/{deck_id}/outline"
    if status in {"building", "failed"}:
        return f"{web_base()}/decks/{deck_id}/build"
    return f"{web_base()}/decks/{deck_id}"


NEXT = {
    "interview": "The Strategist has a few questions. Call get_interview, ask the user, then answer_interview "
                 "(or skip_interview to draft the outline now).",
    "draft": "The Strategist is drafting the outline. Call wait_until_ready (or get_outline in a moment).",
    "outline_ready": "Show the outline to the user. After they approve it, call approve_outline.",
    "building": "The slides are being built. Call wait_until_ready.",
    "ready": "The deck is ready. Review it with get_critic_report, change it with ask, or call export_deck.",
    "failed": "The build stopped. Read `error`; approve_outline again continues from the unfinished slides.",
}


def _outline(deck_id: str) -> dict[str, Any]:
    deck = store.load_deck(deck_id)
    return {
        "deck_id": deck.id, "title": deck.title, "status": deck.status,
        "slides": [{"id": s.id, "index": s.index, "section": s.section, "headline": s.headline,
                    "layout": s.layout, "intent": getattr(s, "intent", None)} for s in deck.slides],
        "web_url": web_url(deck.id, deck.status), "next": NEXT.get(deck.status, ""),
    }


def _activity(deck_id: str, limit: int = 8) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.exec(select(RunRow).where(RunRow.deck_id == deck_id)
                      .order_by(RunRow.started_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [{"role": r.role, "slide_index": r.slide_index, "status": r.status, "summary": r.summary}
            for r in reversed(rows)]


def _status(deck_id: str) -> dict[str, Any]:
    deck = store.load_deck(deck_id)
    row = store.get_deck_row(deck_id)
    ready = sum(1 for s in deck.slides if s.status == "ready")
    out: dict[str, Any] = {
        "deck_id": deck.id, "title": deck.title, "status": deck.status,
        "progress": {"ready": ready, "total": len(deck.slides)},
        "slides": [{"index": s.index, "status": s.status, "headline": s.headline} for s in deck.slides],
        "activity": _activity(deck_id),
        "web_url": web_url(deck.id, deck.status), "next": NEXT.get(deck.status, ""),
    }
    if getattr(row, "error", None):
        out["error"] = row.error
    return out


def _read_sources(paths: list[str]) -> str:
    """Inline readable text files as source material; refuse what cannot be read as text."""
    parts: list[str] = []
    total = 0
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ToolError(f"The source file {raw} does not exist or is not a file.")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise ToolError(f"Lectern can only read text sources for now (.md, .txt, .csv, .json and similar), "
                            f"not {path.suffix or 'files without an extension'}. Convert {path.name} to text first.")
        text = path.read_text(encoding="utf-8", errors="replace")
        room = max(0, min(SOURCE_LIMIT, SOURCES_TOTAL - total))
        if room == 0:
            break
        clipped = text[:room]
        total += len(clipped)
        note = "" if len(clipped) == len(text) else "\n[... clipped]"
        parts.append(f"--- {path.name} ---\n{clipped}{note}")
    return "\n\n".join(parts)


async def _interview(deck_id: str) -> dict[str, Any]:
    state = await interview_mod.get_state(deck_id)
    deck = store.get_deck_row(deck_id)
    return {**state.model_dump(), "deck_status": deck.status, "web_url": web_url(deck_id, deck.status),
            "next": NEXT.get(deck.status, "")}


def _slide_id(deck_id: str, slide_id: str | None, slide_index: int | None) -> str | None:
    if slide_id:
        return store.get_slide_row(deck_id, slide_id).id
    if slide_index is not None:
        for row in store.slide_rows(deck_id):
            if row.position == slide_index:
                return row.id
        raise ToolError(f"This deck has no slide {slide_index}.")
    return None


async def _wait_status(deck_id: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if store.get_deck_row(deck_id).status not in BUSY:
            return
        await asyncio.sleep(0.25)


def build_server() -> MCPServer:
    mcp = MCPServer("lectern", title="Lectern", instructions=INSTRUCTIONS, version="0.1.0",
                    description="Make presentation decks that export as editable PowerPoint files.")

    @mcp.tool(title="Create a deck")
    @_plain_errors
    async def create_deck(
        prompt: Annotated[str, Field(description="What the deck must say: the message, the facts and numbers to "
                                                 "use, and what the audience should do. Plain language.")],
        audience: Annotated[str | None, Field(description="Who will watch it, e.g. 'the board'.")] = None,
        goal: Annotated[str | None, Field(description="What the deck should achieve.")] = None,
        minutes: Annotated[int | None, Field(description="Length of the talk in minutes.", ge=1, le=240)] = None,
        tone: Annotated[str | None, Field(description="Tone, e.g. 'confident and plain'.")] = None,
        slide_count: Annotated[int | None, Field(description="Number of slides wanted.", ge=1, le=60)] = None,
        source_paths: Annotated[list[str] | None, Field(
            description="Absolute paths of text files on this machine to use as source material "
                        "(.md, .txt, .csv, .json...). Figures on the slides come only from the prompt and these.")] = None,
        interview: Annotated[bool, Field(
            description="Let the Strategist ask the user a few questions (audience, goal, length) before drafting. "
                        "Then use get_interview / answer_interview / skip_interview.")] = False,
        wait_for_outline: Annotated[bool, Field(description="Wait (up to 90 s) for the outline and return it.")] = True,
    ) -> dict[str, Any]:
        """Start a new deck. Lectern's Strategist drafts an outline (title and one headline per slide).

        Returns the outline when it is ready. Show it to the user and wait for their approval before calling
        approve_outline; nothing is built until then."""
        full = prompt.strip()
        if source_paths:
            sources = _read_sources(source_paths)
            if sources:
                full = f"{full}\n\nSource material:\n\n{sources}"
        deck = await decks_router.create_deck(DeckCreate(prompt=full, audience=audience, goal=goal, minutes=minutes,
                                                         tone=tone, slide_count=slide_count, interview=interview))
        if interview:
            return {**_outline(deck.id), "interview": await _interview(deck.id)}
        if wait_for_outline:
            await _wait_status(deck.id, 90)
        return _outline(deck.id)

    @mcp.tool(title="Get the interview")
    @_plain_errors
    async def get_interview(deck_id: Annotated[str, Field(description="The deck id.")]) -> dict[str, Any]:
        """The Strategist's questions for a deck created with interview=true: each question's id, text,
        suggested answers (chips) and answer, plus what Lectern has understood so far."""
        return await _interview(deck_id)

    @mcp.tool(title="Answer an interview question")
    @_plain_errors
    async def answer_interview(
        deck_id: Annotated[str, Field(description="The deck id.")],
        question_id: Annotated[str, Field(description="The question's id from get_interview.")],
        answer: Annotated[str, Field(description="The user's answer, in their words.", min_length=1)],
    ) -> dict[str, Any]:
        """Answer one question. When the last one is answered the Strategist drafts the outline; then call
        wait_until_ready and get_outline."""
        await interview_mod.answer(deck_id, interview_mod.AnswerIn(question_id=question_id, answer=answer))
        return await _interview(deck_id)

    @mcp.tool(title="Skip interview questions")
    @_plain_errors
    async def skip_interview(
        deck_id: Annotated[str, Field(description="The deck id.")],
        question_id: Annotated[str | None, Field(description="Skip just this question. Omit to skip every "
                                                             "remaining question and draft the outline now.")] = None,
    ) -> dict[str, Any]:
        """Skip one question, or all remaining ones (the outline is then drafted from the prompt)."""
        await interview_mod.skip(deck_id, interview_mod.SkipIn(question_id=question_id, all=question_id is None))
        return await _interview(deck_id)

    @mcp.tool(title="Get the outline")
    @_plain_errors
    async def get_outline(deck_id: Annotated[str, Field(description="The deck id.")]) -> dict[str, Any]:
        """The deck's title and slides (id, index, section, headline, layout, intent). Show this to the user
        before approve_outline."""
        return _outline(deck_id)

    @mcp.tool(title="Edit the outline")
    @_plain_errors
    async def update_outline(
        deck_id: Annotated[str, Field(description="The deck id.")],
        slides: Annotated[list[OutlineSlideIn], Field(
            description="The full new outline, in order. Keep a slide's `id` to keep it; leave `id` out to add a "
                        "slide; slides left out are removed. `headline` is a claim, e.g. 'Churn doubled in Q3'.")],
        title: Annotated[str | None, Field(description="New deck title; omit to keep it.")] = None,
    ) -> dict[str, Any]:
        """Replace the outline: reorder, add, remove or rewrite slides. Then show it to the user again."""
        current = store.get_deck_row(deck_id)
        await decks_router.update_outline(deck_id, OutlineUpdate(title=title or current.title, slides=slides))
        return _outline(deck_id)

    @mcp.tool(title="Redraft the outline")
    @_plain_errors
    async def regenerate_outline(
        deck_id: Annotated[str, Field(description="The deck id.")],
        instruction: Annotated[str | None, Field(description="What to change, e.g. 'make it shorter'.")] = None,
    ) -> dict[str, Any]:
        """Ask the Strategist to redraft the outline, optionally with an instruction. Waits up to 90 s."""
        await decks_router.regenerate_outline(deck_id, RegenerateIn(instruction=instruction))
        await _wait_status(deck_id, 90)
        return _outline(deck_id)

    @mcp.tool(title="Approve the outline and build")
    @_plain_errors
    async def approve_outline(deck_id: Annotated[str, Field(description="The deck id.")]) -> dict[str, Any]:
        """Approve the outline and start building the slides. Human approval step: call this ONLY after the
        user has seen the outline (get_outline) and said to go ahead. Returns at once; use wait_until_ready."""
        await decks_router.approve(deck_id)
        return _status(deck_id)

    @mcp.tool(title="Get status and activity")
    @_plain_errors
    async def get_status(deck_id: Annotated[str, Field(description="The deck id.")]) -> dict[str, Any]:
        """Status (draft, outline_ready, building, ready, failed), progress, each slide's state and the
        latest agent activity."""
        return _status(deck_id)

    @mcp.tool(title="Wait until ready")
    @_plain_errors
    async def wait_until_ready(
        deck_id: Annotated[str, Field(description="The deck id.")],
        timeout_seconds: Annotated[int, Field(description="Longest wait, 1 to 600 seconds.", ge=1, le=MAX_WAIT)] = 180,
    ) -> dict[str, Any]:
        """Wait while the outline is drafted or the slides are built, then return the status. If it is still
        busy when the time is up, the status says so; call again."""
        await _wait_status(deck_id, float(timeout_seconds))
        return _status(deck_id)

    @mcp.tool(title="Get the Critic report")
    @_plain_errors
    async def get_critic_report(deck_id: Annotated[str, Field(description="The deck id.")]) -> dict[str, Any]:
        """Scores (0-100: overall, story, design, editability) and findings per slide with id, rule, severity
        and status (open, fixed, kept)."""
        report = await critic_router.get_report(deck_id)
        return report.model_dump()

    @mcp.tool(title="Fix or keep findings")
    @_plain_errors
    async def fix_findings(
        deck_id: Annotated[str, Field(description="The deck id.")],
        finding_ids: Annotated[list[str] | None, Field(
            description="Findings to act on. Omit to act on every open finding.")] = None,
        action: Annotated[Literal["fix", "keep"], Field(
            description="fix: repair the slide. keep: accept the finding as intended (Lectern remembers it as "
                        "a rule).")] = "fix",
    ) -> dict[str, Any]:
        """Fix (or keep) Critic findings, then return the updated report."""
        if action == "fix" and not finding_ids:
            report = await critic_router.fix_all(deck_id)
            return report.model_dump()
        ids = finding_ids or [f.id for f in (await critic_router.get_report(deck_id)).findings if f.status == "open"]
        for fid in ids:
            await critic_router.act_on_finding(deck_id, fid, FindingAction(action=action))
        return (await critic_router.get_report(deck_id)).model_dump()

    @mcp.tool(title="Ask for a change")
    @_plain_errors
    async def ask(
        deck_id: Annotated[str, Field(description="The deck id.")],
        message: Annotated[str, Field(description="The change in plain language, e.g. 'turn this into a chart'.")],
        slide_index: Annotated[int | None, Field(description="1-based slide number to change. Omit (with "
                                                             "slide_id) to change the whole deck.")] = None,
        slide_id: Annotated[str | None, Field(description="Slide id, instead of slide_index.")] = None,
        timeout_seconds: Annotated[int, Field(description="Longest wait for the result.", ge=1, le=MAX_WAIT)] = 120,
    ) -> dict[str, Any]:
        """Ask Lectern's Editor for a change to one slide or the whole deck, and wait for the result."""
        target = _slide_id(deck_id, slide_id, slide_index)
        out = await ask_router.ask(deck_id, AskIn(scope="slide" if target else "deck", slide_id=target,
                                                  message=message))
        deadline = time.monotonic() + timeout_seconds
        row: MessageRow | None = None
        while time.monotonic() < deadline:
            with session() as s:
                row = s.get(MessageRow, out.message_id)
            if row is None or row.status != "pending":
                break
            await asyncio.sleep(0.25)
        status = row.status if row else "failed"
        deck = store.get_deck_row(deck_id)
        changed = [r.position for r in store.slide_rows(deck_id) if row and r.id in (row.changed_slide_ids or [])]
        return {"message_id": out.message_id, "status": status,
                "result": (row.result or row.text) if row and status != "pending" else None,
                "changed_slides": changed, "web_url": web_url(deck_id, deck.status)}

    @mcp.tool(title="Edit a slide directly")
    @_plain_errors
    async def edit_slide(
        deck_id: Annotated[str, Field(description="The deck id.")],
        slide_index: Annotated[int | None, Field(description="1-based slide number.")] = None,
        slide_id: Annotated[str | None, Field(description="Slide id, instead of slide_index.")] = None,
        headline: Annotated[str | None, Field(description="New headline.")] = None,
        notes: Annotated[str | None, Field(description="New speaker notes.")] = None,
        layout: Annotated[str | None, Field(description="New layout id, e.g. 'chart', 'two_column'.")] = None,
    ) -> dict[str, Any]:
        """Set a slide's headline, speaker notes or layout exactly as given (no AI). For anything else use ask."""
        target = _slide_id(deck_id, slide_id, slide_index)
        if target is None:
            raise ToolError("Give slide_index or slide_id.")
        try:
            patch = SlidePatch(headline=headline, notes=notes, layout=layout)  # type: ignore[arg-type]
        except ValueError as error:
            raise ToolError(f"That edit is not valid: {error}") from error
        slide = await slides_router.patch_slide(deck_id, target, patch)
        return {"slide": slide.model_dump(exclude_none=True),
                "web_url": web_url(deck_id, store.get_deck_row(deck_id).status)}

    @mcp.tool(title="List decks")
    @_plain_errors
    async def list_decks() -> dict[str, Any]:
        """Every deck in Lectern: id, title, status, slide count, progress, last change, link."""
        decks = [{**d.model_dump(), "web_url": web_url(d.id, d.status)} for d in store.list_decks()]
        return {"decks": decks}

    @mcp.tool(title="Export the deck")
    @_plain_errors
    async def export_deck(
        deck_id: Annotated[str, Field(description="The deck id.")],
        format: Annotated[Literal["pptx"], Field(description="File format. Only pptx for now.")] = "pptx",
        include_notes: Annotated[bool, Field(description="Include speaker notes.")] = True,
    ) -> dict[str, Any]:
        """Export an editable PowerPoint file. Returns the path on disk, a download link, a web link and the
        editability report (how many objects are native text boxes, charts and tables)."""
        out = await export_router.export_deck(deck_id, ExportIn(format=format, include_notes=include_notes))
        path = config.exports_dir() / out.file_id / out.filename
        return {"path": str(path.resolve()), "filename": out.filename, "bytes": out.bytes,
                "download_url": f"{api_base()}/api/files/{out.file_id}",
                "web_url": f"{web_base()}/decks/{deck_id}/export", "report": out.report.model_dump()}

    @mcp.resource("lectern://decks/{deck_id}", name="deck", mime_type="application/json",
                  description="The full deck: brief, theme and every slide's content and notes.")
    def deck_resource(deck_id: str) -> str:
        try:
            return store.load_deck(deck_id).model_dump_json(exclude_none=True)
        except store.NotFound as error:
            raise ResourceError(str(error)) from error

    @mcp.resource("lectern://decks/{deck_id}/outline", name="outline", mime_type="application/json",
                  description="The deck's title and slide headlines, in order.")
    def outline_resource(deck_id: str) -> str:
        try:
            return json.dumps(_outline(deck_id), ensure_ascii=False)
        except store.NotFound as error:
            raise ResourceError(str(error)) from error

    return mcp
