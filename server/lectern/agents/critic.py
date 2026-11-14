"""Critic: the deterministic lint, the deck report, and fix / keep / reopen on findings."""
from __future__ import annotations

from sqlmodel import select

from .. import store
from ..db import session
from ..engine import lint
from ..engine.place import place_deck
from ..events import bus
from ..export.report import predicted_editability
from ..llm.base import LLMError
from ..models import FindingRow, RuleRow
from ..schema import CriticReport, Finding
from . import apply, editor, fixes, runs

# The standing rule written when the user keeps a finding of each kind.
KEEP_RULES = {
    "text_overflow": "Tight text is acceptable when I keep it.",
    "min_font": "Small text is acceptable when I keep it.",
    "too_many_bullets": "It is fine for a list to have more than 5 bullets.",
    "long_bullet": "It is fine for a bullet to run longer than 16 words.",
    "long_headline": "It is fine for a headline to run longer than 12 words.",
    "headline_not_claim": "Topic-style headlines are fine; do not rewrite them as claims.",
    "missing_notes": "Slides do not need speaker notes.",
    "chart_too_many_series": "Charts may show more than 5 series.",
    "chart_wrong_kind": "Keep the chart types I choose.",
    "number_mismatch": "Numbers in the notes may differ from the slide's data.",
    "empty_slot": "A layout may be left with an empty slot.",
    "contrast": "Low-contrast text is acceptable when I keep it.",
    "rule_violation": "Leave a flagged word in place where I keep it.",
    "placeholder_text": "Placeholder text on a slide is fine; I will fill it in myself.",
}


def report(deck_id: str) -> CriticReport:
    """Re-lint every slide and build the deck report."""
    deck = store.load_deck(deck_id)
    for slide in deck.slides:
        store.lint_and_sync(deck_id, slide.id, announce=False)
    findings = store.findings_for(deck_id)
    open_by_slide: dict[str, list[Finding]] = {}
    for finding in findings:
        if finding.status == "open":
            open_by_slide.setdefault(finding.slide_id, []).append(finding)

    def scores(rules: frozenset[str] | None) -> list[int]:
        out = []
        for slide in deck.slides:
            penalty = sum(lint.PENALTY.get(f.severity, 0) for f in open_by_slide.get(slide.id, [])
                          if rules is None or f.rule in rules)
            out.append(max(0, 100 - penalty))
        return out

    return CriticReport(score=lint.mean(scores(None)), story=lint.mean(scores(lint.STORY_RULES)),
                        design=lint.mean(scores(lint.DESIGN_RULES)),
                        editability=predicted_editability(place_deck(deck.slides, deck.theme)),
                        findings=findings)


def _finding(deck_id: str, finding_id: str) -> FindingRow:
    with session() as s:
        row = s.get(FindingRow, finding_id)
    if row is None or row.deck_id != deck_id:
        raise store.NotFound("That finding does not exist. The slide may have changed since the report was made.")
    return row


def _as_finding(deck_id: str, finding_id: str) -> Finding:
    row = _finding(deck_id, finding_id)
    return store.to_finding(row, store.get_slide_row(deck_id, row.slide_id).position)


async def fix(deck_id: str, finding_id: str) -> Finding:
    """Fix one finding. Mechanical rules are fixed in code; the rest go to the Editor."""
    row = _finding(deck_id, finding_id)
    if row.status == "fixed":
        return _as_finding(deck_id, finding_id)
    deck = store.load_deck(deck_id)
    slide = next((s for s in deck.slides if s.id == row.slide_id), None)
    if slide is None:
        raise store.NotFound("That slide does not exist in this deck.")
    key = row.key.split(":", 1)[1] if ":" in row.key else ""
    rules = store.rule_texts()
    slide_row = store.get_slide_row(deck_id, slide.id)
    run = runs.start(deck_id, "editor", f"Editor is fixing \"{row.title.lower()}\" on slide {slide.index}.",
                     slide_row)
    try:
        fixed = fixes.fix_issue(slide, row.rule, key, rules)
        result = None
        if fixed is None or fixed == slide:
            edit, result = await editor.edit_slide(
                deck.brief.model_dump(exclude_none=True), slide, "", rules,
                finding={"rule": row.rule, "key": key, "title": row.title, "detail": row.detail})
            fixed = apply.patched(slide, headline=edit.headline, layout=edit.layout, nodes=edit.nodes,
                                  notes=edit.notes)
        else:
            fixed = apply.patched(fixed)
        apply.save(deck_id, fixed, f"Critic fix: {row.title}")
    except LLMError as error:
        runs.finish(run, f"Editor could not fix slide {slide.index}: {error}", failed=True, error=str(error))
        raise
    after = _finding(deck_id, finding_id)
    done = after.status == "fixed"
    runs.finish(run, (f"Editor fixed \"{row.title.lower()}\" on slide {slide.index}." if done else
                      f"Editor could not fully fix \"{row.title.lower()}\" on slide {slide.index}; "
                      "it needs your judgement."), result, model="fixes")
    return _as_finding(deck_id, finding_id)


def keep(deck_id: str, finding_id: str) -> Finding:
    """Accept a finding as intentional and remember it as a standing rule."""
    row = _finding(deck_id, finding_id)
    source = f"{store.CRITIC_RULE_PREFIX}{row.rule}"
    with session() as s:
        rule = s.exec(select(RuleRow).where(RuleRow.source == source)).first()
        if rule is None:
            rule = RuleRow(text=KEEP_RULES.get(row.rule, f"Do not flag \"{row.title}\"."), source=source)
            s.add(rule)
        fresh = s.get(FindingRow, finding_id)
        assert fresh is not None
        fresh.status = "kept"
        fresh.rule_id = rule.id
        s.add(fresh)
        s.commit()
    _rescore(deck_id, row.slide_id)
    bus.publish(deck_id, "finding.updated", {"id": finding_id, "status": "kept"})
    return _as_finding(deck_id, finding_id)


def reopen(deck_id: str, finding_id: str) -> Finding:
    """Put a kept (or fixed) finding back on the list, and drop the rule that keeping it created."""
    row = _finding(deck_id, finding_id)
    with session() as s:
        fresh = s.get(FindingRow, finding_id)
        assert fresh is not None
        if fresh.rule_id:
            rule = s.get(RuleRow, fresh.rule_id)
            if rule is not None:
                s.delete(rule)
        fresh.rule_id = None
        fresh.status = "open"
        s.add(fresh)
        s.commit()
    _rescore(deck_id, row.slide_id)
    after = _finding(deck_id, finding_id)
    bus.publish(deck_id, "finding.updated", {"id": finding_id, "status": after.status})
    return _as_finding(deck_id, finding_id)


def _rescore(deck_id: str, slide_id: str) -> None:
    store.lint_and_sync(deck_id, slide_id)
    store.publish_slide(store.get_slide_row(deck_id, slide_id))


async def fix_all(deck_id: str) -> CriticReport:
    """Fix every open finding, one at a time. Findings that resist stay open for the user."""
    current = report(deck_id)
    attempted: set[str] = set()
    for _ in range(200):
        target = next((f for f in current.findings if f.status == "open" and f.id not in attempted), None)
        if target is None:
            break
        attempted.add(target.id)
        try:
            await fix(deck_id, target.id)
        except (LLMError, store.NotFound):
            continue
        current = report(deck_id)
    return report(deck_id)
