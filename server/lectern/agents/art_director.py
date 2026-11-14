"""Art Director: confirms the planned layout for the written content, or picks a better one."""
from __future__ import annotations

from typing import Any

from ..llm import router
from ..llm.base import LLMRequest, LLMResult
from ..schema import Slide
from . import prompts
from .contracts import LayoutChoice, schema_of
from .writer import slide_content


async def choose_layout(slide: Slide, neighbours: list[str], rules: list[str],
                        findings: list[dict[str, Any]] | None = None) -> tuple[LayoutChoice, LLMResult]:
    task = (f"Slide {slide.index} was planned with the `{slide.layout}` layout. Look at the content that was "
            "written. Keep the layout if the content fills its required slots and reads well in it; otherwise "
            "choose the layout id that fits the content better. Avoid repeating the layout of the slide before "
            "it unless the content calls for it.")
    extra = "The Critic's findings on this slide:\n" + prompts.as_json(findings) if findings else ""
    request = LLMRequest(
        role="art_director", task="choose_layout", system=prompts.system_text(),
        prompt=prompts.join(task, prompts.rules_block(rules),
                            "The slide:\n" + prompts.as_json(slide_content(slide)),
                            f"Layouts of the slides around it: {', '.join(neighbours) or 'none'}", extra),
        schema=schema_of(LayoutChoice), tool_name="submit_layout", tool_description="Submit the layout choice.",
        payload={"slide": {**slide_content(slide), "intent": slide.intent}, "neighbours": neighbours,
                 "findings": findings or []},
        max_tokens=2000,
    )
    return await router.complete(request, LayoutChoice)
