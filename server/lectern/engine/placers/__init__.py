"""One placer per layout id."""
from __future__ import annotations

from typing import Callable

from ..canvas import Canvas
from . import content, opening

PLACERS: dict[str, Callable[[Canvas], None]] = {
    "title": opening.title,
    "agenda": opening.agenda,
    "section": opening.section,
    "big_idea": opening.big_idea,
    "bullets": content.bullets,
    "two_column": content.two_column,
    "three_column": content.three_column,
    "process": content.process,
    "timeline": content.timeline,
    "chart": content.chart,
    "dashboard": content.dashboard,
    "table": content.table,
    "quote": opening.quote,
    "case_study": content.case_study,
    "diagram": content.diagram,
    "team": content.team,
    "summary": content.summary,
    "next_steps": content.next_steps,
    "closing": opening.closing,
    "appendix": content.appendix,
    "big_number": opening.big_number,
}
