"""The Strategist's interview before the outline (U04). See lectern/interview.py."""
from __future__ import annotations

from fastapi import APIRouter

from .. import interview
from ..interview import AnswerIn, InterviewState, SkipIn

router = APIRouter(tags=["interview"])


@router.get("/decks/{deck_id}/interview", response_model=InterviewState)
async def get_interview(deck_id: str) -> InterviewState:
    return await interview.get_state(deck_id)


@router.post("/decks/{deck_id}/interview/answer", response_model=InterviewState)
async def answer(deck_id: str, body: AnswerIn) -> InterviewState:
    return await interview.answer(deck_id, body)


@router.post("/decks/{deck_id}/interview/skip", response_model=InterviewState)
async def skip(deck_id: str, body: SkipIn | None = None) -> InterviewState:
    return await interview.skip(deck_id, body or SkipIn())
