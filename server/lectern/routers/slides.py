"""Slides: render one, edit by hand, undo."""
from __future__ import annotations

from fastapi import APIRouter

from .. import store
from ..agents import apply
from ..engine.place import context_for, place
from ..schema import RenderedSlide, Slide, SlidePatch

router = APIRouter(tags=["slides"])


@router.get("/decks/{deck_id}/slides/{slide_id}/render", response_model=RenderedSlide,
            response_model_exclude_none=True)
async def render_slide(deck_id: str, slide_id: str) -> RenderedSlide:
    deck = store.load_deck(deck_id)
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise store.NotFound("That slide does not exist in this deck.")
    return place(slide, deck.theme, context_for(deck.slides, slide))


@router.patch("/decks/{deck_id}/slides/{slide_id}", response_model=Slide, response_model_exclude_none=True)
async def patch_slide(deck_id: str, slide_id: str, body: SlidePatch) -> Slide:
    """Manual edit. The slide is normalised for its layout, versioned and re-linted."""
    row = store.get_slide_row(deck_id, slide_id)
    if not store.editable(row):
        raise store.Conflict("This slide is being worked on by an agent. Try again in a moment.")
    slide = store.to_slide(row)
    nodes = body.nodes
    headline = body.headline
    if nodes is not None and headline is None:
        # Editing the headline text box on the canvas arrives as a changed headline node.
        typed = next((n.value for n in nodes if n.type == "text" and n.role == "headline"), None)
        if typed and typed.strip():
            headline = typed
    changed = apply.patched(slide, headline=headline, layout=body.layout, nodes=nodes, notes=body.notes)
    apply.save(deck_id, changed, "Manual edit", section=body.section)
    store.publish_deck(deck_id)
    return store.to_slide(store.get_slide_row(deck_id, slide_id))


@router.post("/decks/{deck_id}/slides/{slide_id}/undo", response_model=Slide, response_model_exclude_none=True)
async def undo_slide(deck_id: str, slide_id: str) -> Slide:
    store.undo_slide(deck_id, slide_id)
    store.lint_and_sync(deck_id, slide_id)
    row = store.get_slide_row(deck_id, slide_id)
    store.publish_slide(row)
    return store.to_slide(row)
