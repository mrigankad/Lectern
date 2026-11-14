"""Layout registry: one typed layout per pattern in references/layout-patterns.md.

Each layout names the pattern it implements (name, purpose and "best for" are read from the
markdown) and declares its slots: which nodes it places and which of them are required.
"""
from __future__ import annotations

from functools import lru_cache
from typing import get_args

from .. import knowledge
from ..schema import LayoutId, LayoutInfo, Slot

LAYOUT_IDS: tuple[str, ...] = get_args(LayoutId)

HEADLINE = Slot(name="headline", type="text", role="headline", required=True,
                description="The slide's claim, one sentence.")
EYEBROW = Slot(name="eyebrow", type="text", role="eyebrow",
               description="Short section label above the headline. Falls back to the slide's section.")
SUBHEAD = Slot(name="subhead", type="text", role="subhead", description="One supporting line.")
BODY = Slot(name="body", type="text", role="body", description="A short paragraph of supporting text.")
CAPTION = Slot(name="caption", type="text", role="caption", description="Source, date or contact line.")


def _items(name: str, style: str, low: int, high: int, description: str, required: bool = True,
           accepts: tuple[str, ...] = ("bullets",)) -> Slot:
    return Slot(name=name, type="items", style=style, required=required, accepts=list(accepts),
                min_items=low, max_items=high, description=description)


# layout id -> (pattern name in layout-patterns.md, slots after the headline)
_SPEC: dict[str, tuple[str, list[Slot]]] = {
    "title": ("Title Slide", [EYEBROW, SUBHEAD, CAPTION]),
    "agenda": ("Agenda / Roadmap", [EYEBROW, _items("items", "steps", 2, 8, "Section names, in order.")]),
    "section": ("Section Divider", [SUBHEAD]),
    "big_idea": ("Single Big Idea", [EYEBROW, BODY, CAPTION]),
    "bullets": ("Bullet List", [EYEBROW, SUBHEAD,
                Slot(name="bullets", type="bullets", required=True, accepts=["items"], min_items=2, max_items=5,
                     description="3-5 parallel bullets.")]),
    "two_column": ("Two-Column", [EYEBROW, _items("columns", "columns", 2, 2,
                   "Two columns: a title and body each. Separate lines in a body with newlines.")]),
    "three_column": ("Three-Column", [EYEBROW, _items("columns", "columns", 3, 3, "Three items of equal weight.")]),
    "process": ("Process / Steps", [EYEBROW, _items("steps", "steps", 3, 5, "Steps in order, a title and one line each.")]),
    "timeline": ("Timeline", [EYEBROW, _items("milestones", "timeline", 3, 6,
                 "Milestones in order; `label` holds the date or phase.")]),
    "chart": ("Data / Chart", [EYEBROW,
              Slot(name="chart", type="chart", required=True, description="One chart with its categories and series."),
              Slot(name="takeaway", type="text", role="body", description="One or two sentences on what the chart shows."),
              CAPTION]),
    "dashboard": ("Dashboard / Metrics", [EYEBROW,
                  Slot(name="stats", type="stat", required=True, min_items=2, max_items=6,
                       description="3-6 metrics, each a value with a caption."),
                  BODY]),
    "table": ("Comparison Table", [EYEBROW,
              Slot(name="table", type="table", required=True, description="Header row plus up to 7 rows."),
              CAPTION]),
    "quote": ("Quote / Testimonial", [EYEBROW,
              Slot(name="quote", type="quote", required=True, description="The quotation and who said it.")]),
    "case_study": ("Case Study", [EYEBROW,
                   _items("story", "columns", 3, 3, "Challenge, solution and results."),
                   Slot(name="stat", type="stat", description="The headline outcome."),
                   Slot(name="quote", type="quote", description="A short client quote.")]),
    "diagram": ("Architecture / Diagram", [EYEBROW,
                _items("parts", "steps", 2, 6, "The parts of the system in flow order, drawn as connected boxes."),
                CAPTION]),
    "team": ("Team / Contributors", [EYEBROW, _items("people", "columns", 2, 6,
             "People: title is the name, label the role, body a one-line bio.", accepts=())]),
    "summary": ("Summary / Key Takeaways", [EYEBROW,
                Slot(name="takeaways", type="bullets", required=True, accepts=["items"], min_items=2, max_items=5,
                     description="3-5 takeaways.")]),
    "next_steps": ("Next Steps / CTA", [EYEBROW, _items("actions", "steps", 2, 5,
                   "Actions: title is the action, label the owner and date.")]),
    "closing": ("Thank You / Q&A", [SUBHEAD, CAPTION]),
    "appendix": ("Appendix", [EYEBROW,
                 Slot(name="content", type="table", required=True, accepts=["bullets", "text", "chart", "items"],
                      description="Backup detail: a table, bullets, a chart or a paragraph.")]),
    "big_number": ("Single Big Idea", [EYEBROW,
                   Slot(name="stat", type="stat", required=True, description="One number with a caption and source."),
                   BODY,
                   Slot(name="bullets", type="bullets", max_items=3, description="Up to three supporting points.")]),
}

_NAMES = {"big_number": "Big Number", "chart": "Chart", "dashboard": "Dashboard", "table": "Table",
          "closing": "Closing", "quote": "Quote", "process": "Process", "team": "Team", "summary": "Summary",
          "next_steps": "Next Steps", "agenda": "Agenda", "diagram": "Diagram", "title": "Title"}
_PURPOSE = {"big_number": "One number that carries the slide, on an accent block"}

# Layouts where a topic-style headline is expected (the headline need not be a claim).
TOPIC_HEADLINE_LAYOUTS = frozenset({"title", "agenda", "section", "closing", "appendix", "team", "quote"})


@lru_cache(maxsize=1)
def registry() -> dict[str, LayoutInfo]:
    patterns = knowledge.layout_patterns()
    layouts: dict[str, LayoutInfo] = {}
    for layout_id, (pattern_name, slots) in _SPEC.items():
        pattern = patterns.get(pattern_name)
        layouts[layout_id] = LayoutInfo(
            id=layout_id,  # type: ignore[arg-type]
            name=_NAMES.get(layout_id, pattern_name),
            purpose=_PURPOSE.get(layout_id) or (pattern.purpose if pattern else pattern_name),
            best_for=pattern.best_for if pattern else "",
            slots=[HEADLINE, *slots],
        )
    return layouts


def get_layout(layout_id: str) -> LayoutInfo:
    return registry()[layout_id]


def required_slots(layout_id: str) -> list[Slot]:
    return [slot for slot in get_layout(layout_id).slots if slot.required and slot.name != "headline"]
