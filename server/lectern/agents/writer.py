"""Writer: fills a slide's nodes and speaker notes, and revises a slide the Critic sent back."""
from __future__ import annotations

from typing import Any

from ..llm import router
from ..llm.base import LLMRequest, LLMResult
from ..schema import Slide
from . import prompts
from .contracts import SlideDraft, schema_of


def slide_brief(slide: Slide) -> dict[str, Any]:
    return {"index": slide.index, "headline": slide.headline, "layout": slide.layout, "section": slide.section,
            "intent": slide.intent}


def slide_content(slide: Slide) -> dict[str, Any]:
    return {"headline": slide.headline, "layout": slide.layout,
            "nodes": [node.model_dump(exclude_none=True) for node in slide.nodes], "notes": slide.notes}


async def write_slide(brief: dict[str, Any], deck_title: str, outline: list[dict[str, Any]], slide: Slide,
                      rules: list[str], findings: list[dict[str, Any]] | None = None
                      ) -> tuple[SlideDraft, LLMResult]:
    target = slide_brief(slide)
    if findings:
        task = (f"The Critic sent slide {slide.index} back. Fix every finding below and return the whole "
                "slide again. Keep what was fine; change only what the findings require.")
        detail = prompts.join("The slide as it stands:\n" + prompts.as_json(slide_content(slide)),
                              "Findings to fix:\n" + prompts.as_json(findings))
    else:
        task = (f"Write slide {slide.index} of the deck \"{deck_title}\". Fill the slots of the "
                f"`{slide.layout}` layout with content nodes and write the speaker notes. You may sharpen the "
                "headline, but keep its meaning. If the brief and sources cannot fill this slide, do not write "
                "template text: rewrite it as what still needs to be found out (open questions, who answers "
                "them, by when).")
        detail = "The slide to write:\n" + prompts.as_json(target)
    request = LLMRequest(
        role="writer", task="write_slide", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.brief_block(brief), prompts.rules_block(rules),
                            "The outline, for context:\n" + prompts.as_json(outline), detail),
        schema=schema_of(SlideDraft), tool_name="submit_slide", tool_description="Submit the written slide.",
        payload={"brief": brief, "deck_title": deck_title, "outline": outline, "slide": target, "rules": rules,
                 "findings": findings or [], "current": slide_content(slide) if findings else None},
    )
    draft, result = await router.complete(request, SlideDraft)
    if brief.get("data_facts"):
        from ..sources.link import fill_linked  # linked charts take their values from the cells
        draft = draft.model_copy(update={"nodes": fill_linked(list(draft.nodes))})
    return draft, result
