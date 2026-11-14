"""The Strategist's short interview before the outline (U04).

A deck created with `interview: true` waits in status `interview`. The Strategist asks up to three short
questions (who is in the room, what should they do afterwards, how long), each with suggested answers.
Answers go into the brief (audience, goal, minutes), so the outline is drafted from them. When every question
is answered or skipped, or the user skips the rest, the outline starts.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from . import store
from .db import session
from .llm import router as llm
from .llm.base import LLMError, LLMRequest
from .llm.offline.facts import extract
from .models import InterviewRow

log = logging.getLogger("lectern.interview")
KEYS = ("audience", "goal", "minutes")


# ---------------------------------------------------------------- payloads
class Question(BaseModel):
    id: str
    key: str                      # audience | goal | minutes
    text: str
    hint: str = ""
    chips: list[str] = Field(default_factory=list)
    answer: str | None = None
    skipped: bool = False
    from_brief: bool = False      # answered by the new-deck form; shown as answered, with "Change"


class KeyNumber(BaseModel):
    value: str
    label: str
    tone: str = "neutral"         # good | bad | neutral


class Understood(BaseModel):
    audience: str | None = None
    goal: str | None = None
    minutes: int | None = None
    time: str | None = None
    numbers: list[KeyNumber] = Field(default_factory=list)
    ask: str | None = None


class InterviewState(BaseModel):
    deck_id: str
    status: str                   # open | done
    questions: list[Question]
    current: str | None = None    # id of the next unanswered question
    understood: Understood


class AnswerIn(BaseModel):
    question_id: str
    answer: str = Field(min_length=1)


class SkipIn(BaseModel):
    question_id: str | None = None
    all: bool = False             # skip every remaining question and draft the outline


class _DraftQuestion(BaseModel):
    key: str
    text: str
    hint: str = ""
    chips: list[str] = Field(default_factory=list, max_length=6)


class _Draft(BaseModel):
    questions: list[_DraftQuestion]


# ---------------------------------------------------------------- offline questions
_AUDIENCE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("board", "directors"), "Board of directors"),
    (("investor", "series", "seed", "vc", "fund"), "Investors"),
    (("exec", "leadership", "ceo", "cfo", "c-suite"), "Executive team"),
    (("customer", "client", "prospect", "buyer"), "Customers"),
    (("team", "offsite", "all-hands", "all hands", "staff", "engineer"), "My team"),
    (("class", "student", "lecture", "course"), "Students"),
    (("partner",), "Partners"),
]
_DEFAULT_AUDIENCE = ["Executive team", "My team", "Customers", "Investors"]
_GOALS = ["Approve a budget", "Choose between options", "Understand where we stand", "Give us feedback",
          "Change a plan"]


def _cap(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:]


def offline_questions(brief: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = str(brief.get("prompt") or "")
    low = prompt.lower()
    facts = extract(prompt, brief.get("audience"), brief.get("goal"))

    audience: list[str] = []
    if brief.get("audience"):
        audience.append(str(brief["audience"]))
    for words, label in _AUDIENCE_HINTS:
        if any(w in low for w in words):
            audience.append(label)
    audience += _DEFAULT_AUDIENCE

    goals: list[str] = []
    if facts.ask:
        goals.append(_cap(facts.ask)[:60])
    if brief.get("goal"):
        goals.append(str(brief["goal"]))
    if any(w in low for w in ("budget", "fund", "$", "€", "£")):
        goals.append("Approve a budget")
    goals += _GOALS

    count = brief.get("slide_count")
    guess = max(5, min(30, int(count) if count else 10))
    lengths = [f"{m} minutes" for m in (5, 10, 15, 20, 30, 45)]
    suggested = f"{min((5, 10, 15, 20, 30), key=lambda m: abs(m - guess))} minutes"
    minutes = [suggested] + lengths

    return [
        {"key": "audience", "text": "Who is in the room?",
         "hint": "Say who they are and what they already know. It sets the vocabulary.", "chips": audience},
        {"key": "goal", "text": "What should they do afterwards?",
         "hint": "Pick the one thing. Every slide will point at it.", "chips": goals},
        {"key": "minutes", "text": "How long do you have?",
         "hint": "It sets how many slides there are and how much each one says.", "chips": minutes},
    ]


def _dedupe(items: list[str], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = item.strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out[:limit]


async def _generate(brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Questions from the Strategist's model; the offline set when there is no model or it fails."""
    fallback = offline_questions(brief)
    provider, _model = llm.resolve("strategist")
    if provider.id != "offline":
        from .agents import prompts
        from .agents.contracts import schema_of
        task = ("Before drafting the outline, ask the user up to three short questions, one for each key: "
                "'audience' (who is in the room), 'goal' (what they should do afterwards) and 'minutes' (how "
                "long the talk is). For each, give 3 to 5 short suggested answers (chips, under 7 words each) "
                "that fit this prompt specifically, most likely first.")
        request = LLMRequest(role="strategist", task="interview", system=prompts.system_text(),
                             prompt=prompts.join(task, prompts.brief_block(brief)), schema=schema_of(_Draft),
                             tool_name="submit_questions", tool_description="Submit the interview questions.",
                             payload={"brief": brief}, max_tokens=2000)
        try:
            draft, _ = await llm.complete(request, _Draft)
            by_key = {q.key: q for q in draft.questions if q.key in KEYS}
            for item in fallback:
                got = by_key.get(item["key"])
                if got and got.chips:
                    item.update(text=got.text.strip() or item["text"], hint=got.hint.strip() or item["hint"],
                                chips=got.chips)
        except (LLMError, Exception):  # noqa: BLE001 - a failed suggestion must never block the interview
            log.warning("interview questions fell back to the offline set", exc_info=True)
    known = brief_answers(brief)
    return [{"id": f"q{i}", **item, "chips": _dedupe(item["chips"]), "answer": known.get(item["key"]),
             "skipped": False, "from_brief": item["key"] in known}
            for i, item in enumerate(fallback, start=1)]


def brief_answers(brief: dict[str, Any]) -> dict[str, str]:
    """Answers the new-deck form already gave (audience, goal, minutes): those questions are not asked."""
    out: dict[str, str] = {}
    for key in ("audience", "goal"):
        if str(brief.get(key) or "").strip():
            out[key] = str(brief[key]).strip()[:300]
    if brief.get("minutes"):
        out["minutes"] = f"{int(brief['minutes'])} minutes"
    return out


# ---------------------------------------------------------------- state
def parse_minutes(text: str) -> int | None:
    low = text.lower()
    match = re.search(r"(\d+(?:\.\d+)?)", low)
    if not match:
        return 60 if "hour" in low else None
    value = float(match.group(1))
    if "hour" in low or re.search(r"\d\s*h\b", low):
        value *= 60
    return max(1, min(240, round(value)))


def _row(deck_id: str) -> InterviewRow | None:
    with session() as s:
        return s.get(InterviewRow, deck_id)


def _understood(brief: dict[str, Any], questions: list[dict[str, Any]]) -> Understood:
    facts = extract(str(brief.get("prompt") or ""), brief.get("audience"), brief.get("goal"))
    answers = {q["key"]: q.get("answer") for q in questions}
    numbers: list[KeyNumber] = []
    for metric in facts.metrics[:3]:
        tone = "good" if metric.good is True else "bad" if metric.good is False else "neutral"
        value = metric.value
        if metric.kind == "change" and metric.direction:
            value = ("+" if metric.direction == "up" else "−") + value.lstrip("+-")
        numbers.append(KeyNumber(value=value, label=metric.caption(), tone=tone))
    minutes = parse_minutes(answers["minutes"]) if answers.get("minutes") else brief.get("minutes")
    return Understood(audience=answers.get("audience"), goal=answers.get("goal"), minutes=minutes,
                      time=answers.get("minutes"), numbers=numbers, ask=facts.ask)


def to_state(deck_id: str, row: InterviewRow) -> InterviewState:
    brief = store.get_deck_row(deck_id).brief or {}
    questions = [Question.model_validate(q) for q in row.questions]
    current = next((q.id for q in questions if q.answer is None and not q.skipped), None)
    return InterviewState(deck_id=deck_id, status=row.status, questions=questions,
                          current=current if row.status == "open" else None,
                          understood=_understood(brief, row.questions))


async def get_state(deck_id: str) -> InterviewState:
    deck = store.get_deck_row(deck_id)
    row = _row(deck_id)
    if row is None:
        if deck.status != "interview":
            raise store.NotFound("This deck has no interview.")
        questions = await _generate(deck.brief or {})
        row = _row(deck_id)           # another request may have made it while the model was answering
        if row is None:
            row = InterviewRow(deck_id=deck_id, questions=questions)
            with session() as s:
                s.add(row)
                s.commit()
            if all(q.get("answer") for q in questions):
                _finish(deck_id, questions)   # the brief answered everything: nothing to ask
                row = _row(deck_id)
    return to_state(deck_id, row)  # type: ignore[arg-type]


def _save(deck_id: str, questions: list[dict[str, Any]], status: str) -> None:
    with session() as s:
        row = s.get(InterviewRow, deck_id)
        assert row is not None
        row.questions = questions
        row.status = status
        s.add(row)
        s.commit()


def _finish(deck_id: str, questions: list[dict[str, Any]]) -> None:
    """Fold the answers into the brief and start the outline."""
    from .agents.pipeline import pipeline

    deck = store.get_deck_row(deck_id)
    brief = dict(deck.brief or {})
    for q in questions:
        answer = (q.get("answer") or "").strip()
        if not answer:
            continue
        if q["key"] == "minutes":
            minutes = parse_minutes(answer)
            if minutes:
                brief["minutes"] = minutes
        else:
            brief[q["key"]] = answer
    _save(deck_id, questions, "done")
    store.update_deck(deck_id, brief=brief)
    pipeline.start_outline(deck_id)


def _open_row(deck_id: str) -> InterviewRow:
    deck = store.get_deck_row(deck_id)
    row = _row(deck_id)
    if row is None or deck.status != "interview" or row.status != "open":
        raise store.Conflict("The interview is over. The Strategist is working from your answers.")
    return row


async def answer(deck_id: str, body: AnswerIn) -> InterviewState:
    await get_state(deck_id)
    row = _open_row(deck_id)
    questions = [dict(q) for q in row.questions]
    target = next((q for q in questions if q["id"] == body.question_id), None)
    if target is None:
        raise store.NotFound("That question does not exist.")
    target["answer"] = body.answer.strip()[:300]
    target["skipped"] = False
    target["from_brief"] = False
    if all(q.get("answer") or q.get("skipped") for q in questions):
        _finish(deck_id, questions)
    else:
        _save(deck_id, questions, "open")
    return to_state(deck_id, _row(deck_id))  # type: ignore[arg-type]


async def skip(deck_id: str, body: SkipIn) -> InterviewState:
    await get_state(deck_id)
    row = _open_row(deck_id)
    questions = [dict(q) for q in row.questions]
    for q in questions:
        if q.get("answer"):
            continue
        if body.all or q["id"] == body.question_id or (body.question_id is None and not q.get("skipped")):
            q["skipped"] = True
            if not body.all:
                break
    if all(q.get("answer") or q.get("skipped") for q in questions):
        _finish(deck_id, questions)
    else:
        _save(deck_id, questions, "open")
    return to_state(deck_id, _row(deck_id))  # type: ignore[arg-type]
