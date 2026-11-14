"""Ask: chat edits on one slide or the whole deck. The result arrives by `message.updated` events."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlmodel import select

from .. import store
from ..agents.pipeline import pipeline
from ..db import session
from ..models import MessageRow
from ..schema import AskIn, AskOut, Message

router = APIRouter(tags=["ask"])


@router.post("/decks/{deck_id}/ask", response_model=AskOut)
async def ask(deck_id: str, body: AskIn) -> AskOut:
    deck = store.get_deck_row(deck_id)
    if deck.status in {"draft", "building"}:
        raise store.Conflict("The deck is still being generated. Ask for changes once it is ready.")
    slide_id = None
    if body.scope == "slide":
        if not body.slide_id:
            raise store.Conflict("Choose a slide to change, or ask about the whole deck.")
        slide_id = store.get_slide_row(deck_id, body.slide_id).id
    user = MessageRow(deck_id=deck_id, role="user", scope=body.scope, slide_id=slide_id,
                      text=body.message.strip(), status="done")
    # The pending assistant row carries the question for the Editor; its text becomes the answer when done.
    reply = MessageRow(deck_id=deck_id, role="assistant", scope=body.scope, slide_id=slide_id, text=user.text,
                       status="pending")
    with session() as s:
        s.add(user)
        s.add(reply)
        s.commit()
    pipeline.start_ask(deck_id, reply.id)
    return AskOut(message_id=reply.id)


@router.get("/decks/{deck_id}/messages", response_model=list[Message])
async def messages(deck_id: str) -> list[Message]:
    store.get_deck_row(deck_id)
    with session() as s:
        rows = s.exec(select(MessageRow).where(MessageRow.deck_id == deck_id)
                      .order_by(MessageRow.created_at, MessageRow.role.desc())).all()  # type: ignore[attr-defined]
    return [Message(id=r.id, role=r.role, scope=r.scope, slide_id=r.slide_id,  # type: ignore[arg-type]
                    text="" if (r.role == "assistant" and r.status == "pending") else r.text,
                    status=r.status, result=r.result,  # type: ignore[arg-type]
                    version_ids=r.version_ids or [], changed_slide_ids=r.changed_slide_ids or [],
                    created_at=r.created_at, undone=bool(r.undone_at)) for r in rows]


@router.post("/decks/{deck_id}/messages/{message_id}/undo")
async def undo(deck_id: str, message_id: str) -> dict[str, Any]:
    """Undo one Ask: exactly the versions it created (see store.undo_message for the rule)."""
    store.get_deck_row(deck_id)
    if store.get_deck_row(deck_id).status == "building":
        raise store.Conflict("The deck is being built. Undo once it is ready.")
    result = store.undo_message(deck_id, message_id)
    for slide_id in result["reverted_slide_ids"]:
        store.lint_and_sync(deck_id, slide_id)
    store.publish_deck(deck_id)
    return result
