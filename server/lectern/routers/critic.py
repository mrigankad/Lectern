"""Critic report and actions on findings."""
from __future__ import annotations

from fastapi import APIRouter

from .. import store
from ..agents import critic
from ..schema import CriticReport, Finding, FindingAction

router = APIRouter(tags=["critic"])


@router.get("/decks/{deck_id}/critic", response_model=CriticReport)
async def get_report(deck_id: str) -> CriticReport:
    return critic.report(deck_id)


@router.post("/decks/{deck_id}/critic/findings/{finding_id}", response_model=Finding)
async def act_on_finding(deck_id: str, finding_id: str, body: FindingAction) -> Finding:
    """fix: repair the slide. keep: accept it and remember that as a rule. reopen: put it back on the list.

    A fix that could not resolve the issue returns the finding still `open`.
    """
    store.get_deck_row(deck_id)
    if body.action == "fix":
        finding = await critic.fix(deck_id, finding_id)
    elif body.action == "keep":
        finding = critic.keep(deck_id, finding_id)
    else:
        finding = critic.reopen(deck_id, finding_id)
    store.publish_deck(deck_id)
    return finding


@router.post("/decks/{deck_id}/critic/fix-all", response_model=CriticReport)
async def fix_all(deck_id: str) -> CriticReport:
    deck = store.get_deck_row(deck_id)
    if deck.status in {"draft", "building"}:
        raise store.Conflict("The deck is still being generated. Fix findings once it is ready.")
    report = await critic.fix_all(deck_id)
    store.publish_deck(deck_id)
    return report
