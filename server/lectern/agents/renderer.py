"""Renderer: validates a slide's nodes against its layout's slots and makes it safe to place."""
from __future__ import annotations

from typing import Any

from ..layouts.adapt import adapt_nodes, ensure_headline, missing_slots
from ..llm import router
from ..llm.base import LLMRequest, LLMResult
from ..schema import BulletsNode, ChartNode, ItemsNode, Node, Series, Slide, TableNode, TextNode
from . import prompts
from .contracts import SlideDraft, schema_of
from .writer import slide_content


def _clean(node: Node) -> Node | None:
    """Drop empty content and make data rectangular."""
    if isinstance(node, TextNode):
        return node if node.value.strip() else None
    if isinstance(node, BulletsNode):
        items = [item.strip() for item in node.items if item and item.strip()]
        return node.model_copy(update={"items": items}) if items else None
    if isinstance(node, ItemsNode):
        items = [item for item in node.items if item.title.strip()]
        return node.model_copy(update={"items": items}) if items else None
    if isinstance(node, ChartNode):
        count = len(node.categories)
        series = [Series(name=s.name, values=(list(s.values) + [0.0] * count)[:count]) for s in node.series]
        if not count or not series:
            return None
        return node.model_copy(update={"series": series})
    if isinstance(node, TableNode):
        width = len(node.columns)
        if not width:
            return None
        rows = [(list(row) + [""] * width)[:width] for row in node.rows]
        return node.model_copy(update={"rows": rows})
    return node


def normalize(slide: Slide) -> Slide:
    """Deterministic clean-up: one headline node, no empty nodes, list content in the form the layout draws."""
    nodes = [cleaned for node in slide.nodes if (cleaned := _clean(node)) is not None]
    nodes = adapt_nodes(nodes, slide.layout)
    headline = slide.headline.strip() or "Untitled slide"
    return slide.model_copy(update={"headline": headline, "nodes": ensure_headline(nodes, headline)})


def missing(slide: Slide) -> list[str]:
    return [slot.name for slot in missing_slots(slide.layout, slide.nodes)]


async def repair(brief: dict[str, Any], slide: Slide, rules: list[str]) -> tuple[SlideDraft, LLMResult]:
    """Ask for the content a required slot is missing."""
    gaps = missing(slide)
    task = (f"Slide {slide.index} uses the `{slide.layout}` layout, but these required slots are empty: "
            f"{', '.join(gaps)}. Add the missing nodes using facts from the brief, keep the existing nodes, "
            "and return the whole slide.")
    request = LLMRequest(
        role="renderer", task="repair_slide", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.brief_block(brief), prompts.rules_block(rules),
                            "The slide:\n" + prompts.as_json(slide_content(slide))),
        schema=schema_of(SlideDraft), tool_name="submit_slide", tool_description="Submit the repaired slide.",
        payload={"brief": brief, "slide": {**slide_content(slide), "intent": slide.intent}, "missing": gaps,
                 "rules": rules},
    )
    return await router.complete(request, SlideDraft)
