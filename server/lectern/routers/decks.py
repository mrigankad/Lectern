"""Decks: create, list, outline editing, approve, pause/resume, render, events, runs."""
from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlmodel import select

from .. import store
from ..agents import apply, runs
from ..agents.pipeline import pipeline
from ..db import session
from ..engine.place import place_deck
from ..events import bus
from ..models import DeckRow, RunRow, SlideRow
from ..schema import (Brief, Deck, DeckCreate, DeckPatch, DeckSummary, OutlineUpdate, RegenerateIn, RenderedSlide, Run,
                      TextNode, Theme)

router = APIRouter(tags=["decks"])


def _working_title(prompt: str) -> str:
    first = re.split(r"(?<=[.!?])\s+|\n", prompt.strip(), maxsplit=1)[0].strip(" .")
    words = first.split()
    return (" ".join(words[:8]) + ("…" if len(words) > 8 else "")) or "Untitled deck"


@router.get("/decks", response_model=list[DeckSummary])
async def list_decks() -> list[DeckSummary]:
    return store.list_decks()


@router.post("/decks", response_model=Deck, response_model_exclude_none=True)
async def create_deck(body: DeckCreate) -> Deck:
    brief = Brief(prompt=body.prompt.strip(), audience=body.audience, goal=body.goal, minutes=body.minutes,
                  tone=body.tone, slide_count=body.slide_count, source_ids=body.source_ids or None)
    row = DeckRow(title=_working_title(body.prompt), status="interview" if body.interview else "draft",
                  brief=brief.model_dump(exclude_none=True),
                  theme=Theme().model_dump())
    with session() as s:
        s.add(row)
        s.commit()
    if body.source_ids:
        from ..sources import service as sources
        sources.attach(body.source_ids, row.id)
    if not body.interview:
        pipeline.start_outline(row.id)
    return store.load_deck(row.id)


@router.get("/decks/{deck_id}", response_model=Deck, response_model_exclude_none=True)
async def get_deck(deck_id: str) -> Deck:
    return store.load_deck(deck_id)


@router.patch("/decks/{deck_id}", response_model=Deck, response_model_exclude_none=True)
async def patch_deck(deck_id: str, body: DeckPatch) -> Deck:
    """Rename a deck or change its sidebar icon. Empty strings clear the icon."""
    fields = body.model_dump(exclude_unset=True)
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip() or store.get_deck_row(deck_id).title
    for key in ("icon", "icon_color"):
        if key in fields and not fields[key]:
            fields[key] = None
    store.update_deck(deck_id, **fields)
    store.publish_deck(deck_id)
    return store.load_deck(deck_id)


@router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str) -> dict[str, bool]:
    store.get_deck_row(deck_id)
    pipeline.cancel(deck_id)
    store.delete_deck(deck_id)
    return {"ok": True}


@router.put("/decks/{deck_id}/outline", response_model=Deck, response_model_exclude_none=True)
async def update_outline(deck_id: str, body: OutlineUpdate) -> Deck:
    """Reorder, add, remove and edit outline slides. Slides that keep their id keep their content."""
    deck = store.get_deck_row(deck_id)
    if deck.status in {"draft", "building"} or pipeline.is_running(deck_id):
        raise store.Conflict("The outline cannot be edited while the deck is being generated.")
    if not body.slides:
        raise store.Conflict("An outline needs at least one slide.")
    existing = {row.id: row for row in store.slide_rows(deck_id)}
    kept: set[str] = set()
    for position, item in enumerate(body.slides, start=1):
        headline = item.headline.strip() or "Untitled slide"
        row = existing.get(item.id) if item.id else None
        if row is None:
            with session() as s:
                s.add(SlideRow(deck_id=deck_id, position=position, section=item.section, headline=headline,
                               layout=item.layout, intent=item.intent, status="queued",
                               nodes=[TextNode(role="headline", value=headline).model_dump()]))
                s.commit()
            continue
        kept.add(row.id)
        with session() as s:
            fresh = s.get(SlideRow, row.id)
            assert fresh is not None
            fresh.position = position
            fresh.section = item.section
            if item.intent is not None:
                fresh.intent = item.intent
            s.add(fresh)
            s.commit()
        if headline != row.headline or item.layout != row.layout:
            slide = apply.patched(store.to_slide(store.get_slide_row(deck_id, row.id)), headline=headline,
                                  layout=item.layout)
            apply.save(deck_id, slide, "Outline edit", lint=row.status == "ready", announce=False)
    removed = [slide_id for slide_id in existing if slide_id not in kept]
    store.delete_slides(deck_id, removed)
    rows = store.slide_rows(deck_id)
    status = deck.status
    if status == "ready" and any(r.status != "ready" for r in rows):
        status = "outline_ready"      # new slides need building: approve again to build just those
    store.update_deck(deck_id, title=body.title.strip() or deck.title, status=status)
    store.publish_deck(deck_id)
    return store.load_deck(deck_id)


@router.post("/decks/{deck_id}/outline/regenerate", response_model=Deck, response_model_exclude_none=True)
async def regenerate_outline(deck_id: str, body: RegenerateIn | None = None) -> Deck:
    deck = store.get_deck_row(deck_id)
    if deck.status == "building":
        raise store.Conflict("The deck is being built. Pause or wait before regenerating the outline.")
    pipeline.start_outline(deck_id, (body.instruction if body else None) or None)
    return store.load_deck(deck_id)


@router.post("/decks/{deck_id}/approve", response_model=Deck, response_model_exclude_none=True)
async def approve(deck_id: str) -> Deck:
    deck = store.get_deck_row(deck_id)
    if deck.status == "draft":
        raise store.Conflict("The outline is still being drafted. Approve it once it is ready.")
    if deck.status == "building" and pipeline.is_running(deck_id):
        raise store.Conflict("This deck is already being built.")
    rows = store.slide_rows(deck_id)
    if not rows:
        raise store.Conflict("There is no outline to build yet. Regenerate the outline first.")
    if all(row.status == "ready" for row in rows):
        store.update_deck(deck_id, status="ready", error=None)
        store.publish_deck(deck_id)
        return store.load_deck(deck_id)
    pipeline.start_build(deck_id)
    return store.load_deck(deck_id)


@router.post("/decks/{deck_id}/pause", response_model=Deck, response_model_exclude_none=True)
async def pause(deck_id: str) -> Deck:
    pipeline.pause(deck_id)
    return store.load_deck(deck_id)


@router.post("/decks/{deck_id}/resume", response_model=Deck, response_model_exclude_none=True)
async def resume(deck_id: str) -> Deck:
    pipeline.resume(deck_id)
    return store.load_deck(deck_id)


@router.get("/decks/{deck_id}/render", response_model=list[RenderedSlide], response_model_exclude_none=True)
async def render_deck(deck_id: str) -> list[RenderedSlide]:
    deck = store.load_deck(deck_id)
    return place_deck(deck.slides, deck.theme)


@router.get("/decks/{deck_id}/runs", response_model=list[Run])
async def list_runs(deck_id: str, limit: int = 200) -> list[Run]:
    """Additive to the spec: the activity feed's history, so a reload can show what already happened."""
    store.get_deck_row(deck_id)
    with session() as s:
        rows = s.exec(select(RunRow).where(RunRow.deck_id == deck_id)
                      .order_by(RunRow.started_at.desc()).limit(max(1, min(limit, 1000)))).all()  # type: ignore[attr-defined]
    return [runs.to_run(row) for row in reversed(rows)]


@router.get("/decks/{deck_id}/events")
async def events(deck_id: str) -> StreamingResponse:
    store.get_deck_row(deck_id)
    return StreamingResponse(bus.stream(deck_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})
