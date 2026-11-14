"""The offline provider: deterministic, no network. It answers the same structured requests a model
would, working from the request payload instead of the prompt text."""
from __future__ import annotations

import asyncio
from typing import Any

from ... import config
from ...agents import fixes
from ...engine import lint
from ...layouts.adapt import adapt_nodes, ensure_headline, missing_slots
from ...schema import Slide, StatNode
from ..base import LLMError, LLMRequest, LLMResult
from . import editor, outline, writer
from .facts import Facts, extract

MODEL = "offline-1"


def _facts(payload: dict[str, Any]) -> Facts:
    brief = payload.get("brief") or {}
    prompt = str(brief.get("prompt") or "")
    if brief.get("data_facts"):  # the Analyst's numbers read like more of the brief
        from ...sources.analyst import data_prompt
        prompt = data_prompt(prompt, brief["data_facts"])
    return extract(prompt, brief.get("audience"), brief.get("goal"))


def _slide(data: dict[str, Any]) -> Slide:
    base = {"id": "draft", "index": 1, "headline": "", "layout": "bullets", "nodes": [], "notes": ""}
    return Slide.model_validate({**base, **{k: v for k, v in data.items() if v is not None}})


def _apply_banned(slide: Slide, rules: list[str]) -> Slide:
    for rule_text in rules:
        for term in lint.banned_terms(rule_text):
            slide = fixes.remove_term(slide, term)
    return slide


def _dump(slide: Slide) -> dict[str, Any]:
    return {"headline": slide.headline, "layout": slide.layout,
            "nodes": [n.model_dump(exclude_none=True) for n in slide.nodes], "notes": slide.notes}


class OfflineProvider:
    id = "offline"

    async def complete(self, request: LLMRequest, model: str = MODEL) -> LLMResult:
        delay = config.offline_delay()
        if delay:
            await asyncio.sleep(delay)
        handler = getattr(self, f"_{request.task}", None)
        if handler is None:
            raise LLMError(f"The offline provider cannot do \"{request.task}\".")
        return LLMResult(data=handler(request.payload), provider=self.id, model=MODEL)

    async def test(self) -> tuple[bool, str, list[str] | None]:
        return True, "Built in. Works without a network or an API key.", [MODEL]

    # ------------------------------------------------------------ strategist
    def _outline(self, payload: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(payload)
        brief = payload.get("brief") or {}
        current = payload.get("current") or {}
        deck_type = brief.get("deck_type") or outline.classify_deck(facts.prompt)
        steps = outline.build_steps(facts, deck_type, brief.get("slide_count"), brief.get("minutes"),
                                    payload.get("instruction"), len(current.get("slides") or []) or None)
        slides = [{"section": s.section, "headline": s.headline, "layout": s.layout, "intent": s.intent}
                  for s in steps]
        rules = [str(r) for r in payload.get("rules") or []]
        for entry in slides:
            for rule_text in rules:
                for term in lint.banned_terms(rule_text):
                    entry["headline"] = fixes.remove_term(_slide({"headline": entry["headline"]}), term).headline
        return {"title": outline.deck_title(facts), "deck_type": deck_type, "slides": slides}

    # ------------------------------------------------------------ writer
    def _write_slide(self, payload: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(payload)
        target = payload.get("slide") or {}
        rules = [str(r) for r in payload.get("rules") or []]
        findings = payload.get("findings") or []
        current = payload.get("current")
        if findings and current:
            slide = _slide({**current, "layout": target.get("layout") or current.get("layout"),
                            "intent": target.get("intent")})
            for finding in findings:
                fixed, _summary = editor.fix_finding(slide, finding, facts, rules)
                if fixed is not None:
                    slide = fixed
            return _dump(_apply_banned(slide, rules))
        headline = str(target.get("headline") or "")
        nodes = writer.write_nodes(target, facts, payload.get("outline") or [])
        slide = _slide({"headline": headline, "layout": target.get("layout"),
                        "nodes": [n.model_dump() for n in ensure_headline(nodes, headline)],
                        "notes": writer.write_notes(target, facts)})
        if (payload.get("brief") or {}).get("data_facts"):
            from ...sources.analyst import link_offline_slide
            slide = link_offline_slide(slide, target, payload)
        return _dump(_apply_banned(slide, rules))

    # ------------------------------------------------------------ art director
    def _choose_layout(self, payload: dict[str, Any]) -> dict[str, Any]:
        slide = _slide(payload.get("slide") or {})
        adapted = adapt_nodes(slide.nodes, slide.layout)
        if not missing_slots(slide.layout, adapted):
            return {"layout": slide.layout, "reason": "The content fits this layout."}
        return {"layout": layout_for_nodes(slide), "reason": "The content does not fill the planned layout."}

    # ------------------------------------------------------------ renderer
    def _repair_slide(self, payload: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(payload)
        slide = _slide(payload.get("slide") or {})
        fixed, _summary = editor.fix_finding(slide, {"rule": "empty_slot"}, facts, [])
        return _dump(fixed or slide)

    # ------------------------------------------------------------ editor
    def _edit_slide(self, payload: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(payload)
        slide = _slide(payload.get("slide") or {})
        rules = [str(r) for r in payload.get("rules") or []]
        finding = payload.get("finding")
        if finding:
            changed, summary = editor.fix_finding(slide, finding, facts, rules)
        else:
            changed, summary = editor.edit_slide(slide, str(payload.get("message") or ""), facts)
        if changed is None:
            return {"summary": summary}
        return {**_dump(_apply_banned(changed, rules)), "summary": summary}

    def _edit_deck(self, payload: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(payload)
        message = str(payload.get("message") or "")
        changes = []
        last = editor.HELP
        for data in payload.get("slides") or []:
            slide = _slide(data)
            changed, summary = editor.edit_slide(slide, message, facts)
            if changed is not None and changed != slide:
                changes.append({"slide_id": data.get("id"), **_dump(changed)})
            else:
                last = summary
        if not changes:
            return {"changes": [], "summary": last if last == editor.HELP else
                    "Nothing on any slide needed that change."}
        count = len(changes)
        return {"changes": changes,
                "summary": f"Applied that to {count} slide{'s' if count != 1 else ''}."}


def layout_for_nodes(slide: Slide) -> str:
    """The layout that suits the nodes a slide actually has."""
    types = [n.type for n in slide.nodes]
    stats = sum(1 for n in slide.nodes if isinstance(n, StatNode))
    if "chart" in types:
        return "chart"
    if "table" in types:
        return "table"
    if stats >= 2:
        return "dashboard"
    if stats == 1:
        return "big_number"
    if "quote" in types:
        return "quote"
    for node in slide.nodes:
        if node.type == "items":
            count = len(node.items)  # type: ignore[union-attr]
            style = node.style  # type: ignore[union-attr]
            if style == "timeline":
                return "timeline"
            if style == "steps":
                return "process" if count <= 5 else "bullets"
            return "two_column" if count == 2 else "three_column" if count == 3 else "bullets"
    if "bullets" in types:
        return "bullets"
    return "big_idea"
