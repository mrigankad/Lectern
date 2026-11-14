"""Editor: turns a chat request, or a Critic finding, into a patch on one slide or on the deck."""
from __future__ import annotations

from typing import Any

from ..llm import router
from ..llm.base import LLMRequest, LLMResult
from ..schema import Slide
from . import prompts
from .contracts import DeckEdit, SlideEdit, schema_of
from .writer import slide_content


async def edit_slide(brief: dict[str, Any], slide: Slide, message: str, rules: list[str],
                     finding: dict[str, Any] | None = None) -> tuple[SlideEdit, LLMResult]:
    if finding:
        task = (f"Fix this Critic finding on slide {slide.index} and nothing else: "
                f"{finding.get('title')}. {finding.get('detail')}")
    else:
        task = f"The user asks for a change to slide {slide.index}: {message}"
    task += ("\nReturn only the fields that change (headline, layout, nodes, notes); when nodes change, return "
             "the complete new list. Add a one-sentence summary of what you changed, written to the user.")
    request = LLMRequest(
        role="editor", task="edit_slide", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.brief_block(brief), prompts.rules_block(rules),
                            "The slide:\n" + prompts.as_json(slide_content(slide))),
        schema=schema_of(SlideEdit), tool_name="submit_edit", tool_description="Submit the slide patch.",
        payload={"brief": brief, "slide": {**slide_content(slide), "intent": slide.intent, "id": slide.id},
                 "message": message, "rules": rules, "finding": finding},
    )
    return await router.complete(request, SlideEdit)


async def edit_deck(brief: dict[str, Any], title: str, slides: list[Slide], message: str,
                    rules: list[str]) -> tuple[DeckEdit, LLMResult]:
    listing = [{"id": s.id, "index": s.index, **slide_content(s)} for s in slides]
    task = (f"The user asks for a change across the deck \"{title}\": {message}\n"
            "Return one change per slide that needs to change, identified by slide_id, with only the fields "
            "that change (when nodes change, the complete new list). Leave other slides out. When the user "
            "asks for a shorter deck, also list in remove_slide_ids the slides that repeat another slide or "
            "carry the least weight for the goal (never the title slide or the slide with the ask), and say "
            "which ones you removed in the summary. Add a one-sentence summary of what you changed, written to "
            "the user.")
    request = LLMRequest(
        role="editor", task="edit_deck", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.brief_block(brief), prompts.rules_block(rules),
                            "The slides:\n" + prompts.as_json(listing)),
        schema=schema_of(DeckEdit), tool_name="submit_edit", tool_description="Submit the deck patch.",
        payload={"brief": brief, "title": title, "message": message, "rules": rules,
                 "slides": [{**entry, "intent": s.intent} for entry, s in zip(listing, slides)]},
    )
    return await router.complete(request, DeckEdit)
