"""Strategist: turns the brief into an outline (title, sections, per slide: headline, layout, intent)."""
from __future__ import annotations

from typing import Any

from ..llm import router
from ..llm.base import LLMRequest, LLMResult
from . import prompts
from .contracts import OutlineDraft, schema_of


async def draft_outline(brief: dict[str, Any], rules: list[str], instruction: str | None = None,
                        current: dict[str, Any] | None = None) -> tuple[OutlineDraft, LLMResult]:
    task = ("Plan the outline for this deck. Choose the deck type from the reference knowledge that fits, "
            "follow its typical flow where it helps, and give each slide a headline written as a claim, the "
            "layout id that suits its content, a short section label and a one-line intent. Vary the layouts: "
            "use a chart where there is data to compare, a big_number where one figure carries the point, and "
            "column or step layouts for lists of equal items. Start with a title slide. Plan only slides the "
            "brief and sources can fill: do not plan a breakdown, a quote, a case study or a team slide whose "
            "content is not given. Merge such a point into a neighbouring slide, or plan one slide that names "
            "what still needs to be found out.")
    revise = ""
    if current:
        revise = "The current outline is:\n" + prompts.as_json(current)
    if instruction:
        revise += f"\n\nRevise it as the user asks: {instruction}"
    request = LLMRequest(
        role="strategist", task="outline", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.brief_block(brief), prompts.rules_block(rules), revise.strip()),
        schema=schema_of(OutlineDraft), tool_name="submit_outline",
        tool_description="Submit the deck outline.",
        payload={"brief": brief, "rules": rules, "instruction": instruction, "current": current},
    )
    return await router.complete(request, OutlineDraft)
