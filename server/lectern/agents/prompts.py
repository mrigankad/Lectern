"""Prompt building. The system text is identical for every call so providers can cache it;
everything that varies (brief, rules, the slide in hand) goes in the user prompt."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .. import knowledge
from ..layouts import registry

_PREAMBLE = """You are one of the agents inside Lectern, a tool that writes presentations and exports them \
as editable PowerPoint files. Agents: the Strategist plans the outline, the Writer fills each slide, the Art \
Director picks the layout, the Renderer checks content against the layout's slots, the Critic checks the \
result, and the Editor applies the user's change requests.

A slide is typed data, not free text. It has a headline, a layout id, a list of content nodes and speaker \
notes. Nodes carry content only; the layout engine decides positions and sizes. Node types:
- text: {type:"text", role:"eyebrow"|"subhead"|"body"|"caption", value}
- bullets: {type:"bullets", items:[string]}
- stat: {type:"stat", value, caption?, source?}
- chart: {type:"chart", kind:"bar"|"line"|"area"|"pie", title?, categories:[string], series:[{name, values:[number]}], unit?}
- table: {type:"table", columns:[string], rows:[[string]]}
- quote: {type:"quote", text, attribution?}
- items: {type:"items", style:"columns"|"steps"|"timeline", items:[{title, body?, label?}]}
- image: {type:"image", alt, prompt?}

Writing rules, which the Critic enforces:
- The headline is a claim with a verb, 12 words or fewer ("Churn rose to 4.1% in Q3", not "Churn"). \
Title, agenda, section, closing and appendix slides may use a plain title.
- One idea per slide. At most 5 bullets, each 16 words or fewer, in parallel structure.
- Every number on a slide must come from the brief or the source material. Never invent figures, names or \
quotes. Never write template or instruction text on a slide ("Area 1: name the segment", "Add the \
segment, its share of...", "Insert chart here", "Describe your solution", [brackets], TBD). If a slide needs \
facts the brief and sources do not give, make it an honest "what we still need to find out" slide: the \
headline says what is not known yet, and each item is one open question with who will answer it and by when. \
The Critic blocks a slide with template text.
- The same number must read the same in the headline, the body, the chart and the notes.
- A stat's source is the one cell whose value it shows. A derived figure (growth, a change in points) \nhas no source; say in the notes how it was worked out.
- Speaker notes are required: two to four sentences on what to say that is not on the slide.
- A pie chart has at most 6 slices; a line chart needs at least 3 points; a chart has at most 5 series.
- Fill every required slot of the layout you are given. Do not add a node the layout has no slot for.
- Follow the user's standing rules exactly. They override everything else here.
- Plain, direct language. No filler, no hype."""


@lru_cache(maxsize=1)
def system_text() -> str:
    layouts = []
    for layout in registry().values():
        slots = "; ".join(
            f"{slot.name} ({slot.type}{'/' + slot.style if slot.style else ''}"
            f"{', required' if slot.required else ''}"
            f"{', ' + str(slot.min_items) + '-' + str(slot.max_items) + ' items' if slot.max_items else ''})"
            for slot in layout.slots)
        layouts.append(f"- {layout.id}: {layout.purpose}. Best for: {layout.best_for or 'general use'}. "
                       f"Slots: {slots}")
    return "\n\n".join([
        _PREAMBLE,
        "# Layouts you can use (layout id: purpose, slots)\n" + "\n".join(layouts),
        "# Reference knowledge\n" + knowledge.reference_text(),
    ])


def rules_block(rules: list[str]) -> str:
    if not rules:
        return ""
    return "The user's standing rules (always follow these):\n" + "\n".join(f"- {rule}" for rule in rules)


def brief_block(brief: dict[str, Any]) -> str:
    lines = [f"What the user wants to say:\n{brief.get('prompt', '')}"]
    for key, label in (("audience", "Audience"), ("goal", "Goal"), ("minutes", "Length in minutes"),
                       ("tone", "Tone"), ("deck_type", "Deck type"), ("slide_count", "Target slide count")):
        if brief.get(key):
            lines.append(f"{label}: {brief[key]}")
    if brief.get("data_facts"):
        from .analyst import facts_block  # the Analyst's numbers with their cell/page references
        lines.append("\n" + facts_block(brief))
    return "\n".join(lines)


def as_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


def join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)
