"""List, column, sequence and data layouts. Each starts from the shared frame."""
from __future__ import annotations

from ...schema import BulletsNode, ChartNode, Item, ItemsNode, QuoteNode, StatNode, TableNode
from .. import components
from ..canvas import GAP, Box, Canvas
from ..frame import flow, flow_rest, frame, split_side


def _items(cv: Canvas) -> tuple[int, list[Item]] | None:
    """The slide's list content as items, whether it was written as items or as bullets."""
    entry = cv.bag.take("items")
    if entry and isinstance(entry[1], ItemsNode):
        return entry[0], list(entry[1].items)
    entry = cv.bag.take("bullets")
    if entry and isinstance(entry[1], BulletsNode):
        from ...layouts.adapt import bullet_to_item
        return entry[0], [bullet_to_item(text) for text in entry[1].items]
    return None


def _wide(cv: Canvas) -> bool:
    return any(node.type in {"chart", "table", "items", "image"} for _, node in cv.bag.rest())


# ---------------------------------------------------------------- lists
def bullets(cv: Canvas) -> None:
    box = frame(cv)
    rest = cv.bag.rest()
    flow(cv, rest, box if _wide(cv) else Box(box.x, box.y, 1400, box.h))


def appendix(cv: Canvas) -> None:
    box = frame(cv, max_size=44, min_size=34)
    flow(cv, cv.bag.rest(), box)


def summary(cv: Canvas) -> None:
    """Takeaways as numbered rows."""
    box = frame(cv)
    rows: list[tuple[int | None, str, str | None, str | None]] = []
    entry = cv.bag.take("bullets")
    if entry and isinstance(entry[1], BulletsNode):
        rows = [(entry[0], text, None, None) for text in entry[1].items]
    else:
        found = _items(cv)
        if found:
            rows = [(found[0], item.title, item.body, item.label) for item in found[1]]
    main, side = split_side(cv, box)
    components.numbered_rows(cv, rows[:8], main, max_row=140, title_max=34)
    flow_rest(cv, side)


def next_steps(cv: Canvas) -> None:
    """Actions as rows: a numbered badge, the action, and the owner or date on the right."""
    box = frame(cv)
    found = _items(cv)
    rows = [(found[0], item.title, item.body, item.label) for item in found[1]] if found else []
    main, side = split_side(cv, box)
    components.numbered_rows(cv, rows[:8], main, badge=True, max_row=150, title_max=32)
    flow_rest(cv, side)


# ---------------------------------------------------------------- columns
def two_column(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box)
    if found:
        components.columns(cv, found[0], found[1][:2], main, divider=True)
    flow_rest(cv, side if found else box)


def three_column(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box, 0.74)
    if found:
        components.columns(cv, found[0], found[1], main, numbered=True)
    flow_rest(cv, side if found else box)


def team(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box, 0.74)
    if found:
        components.people(cv, found[0], found[1], main)
    flow_rest(cv, side if found else box)


def case_study(cv: Canvas) -> None:
    """Challenge, solution and results in columns; the outcome as a number; an optional client quote."""
    box = frame(cv)
    found = _items(cv)
    stat = cv.bag.take("stat")
    quote = cv.bag.take("quote")
    quote_h = 170 if quote else 0
    upper = Box(box.x, box.y, box.w, box.h - quote_h - (32 if quote else 0))
    stat_w = 440 if stat else 0
    cols = Box(upper.x, upper.y, upper.w - (stat_w + GAP if stat else 0), upper.h)
    if found:
        components.columns(cv, found[0], found[1][:4], cols)
    if stat and isinstance(stat[1], StatNode):
        components.stat_card(cv, stat[0], stat[1], Box(upper.right - stat_w, upper.y, stat_w, min(upper.h, 360)),
                             emphasis=True, max_size=120)
    if quote and isinstance(quote[1], QuoteNode):
        components.quote_block(cv, quote[0], quote[1], Box(box.x, box.bottom - quote_h, 1500, quote_h), 34)
    cv.bag.mark(cv.bag.rest())


# ---------------------------------------------------------------- sequences
def process(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box, 0.74)
    if found:
        components.steps(cv, found[0], found[1], Box(main.x, main.y + 16, main.w, main.h - 16))
    flow_rest(cv, side if found else box)


def timeline(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box, 0.74)
    if found:
        components.timeline(cv, found[0], found[1], Box(main.x, main.y + 16, main.w, main.h - 16))
    flow_rest(cv, side if found else box)


def diagram(cv: Canvas) -> None:
    box = frame(cv)
    found = _items(cv)
    main, side = split_side(cv, box, 0.74)
    if found:
        components.diagram(cv, found[0], found[1], Box(main.x, main.y + 16, main.w, main.h - 16))
    flow_rest(cv, side if found else box)


# ---------------------------------------------------------------- data
def chart(cv: Canvas) -> None:
    """The chart takes two thirds of the slide; the takeaway sits beside it."""
    box = frame(cv)
    entry = cv.bag.take("chart")
    main, side = split_side(cv, box, 0.68)
    if entry and isinstance(entry[1], ChartNode):
        components.chart_block(cv, entry[0], entry[1], main)
        if side is not None:
            cv.vrule(side.x - GAP / 2, side.y, side.h)
        flow_rest(cv, side)
    else:
        flow_rest(cv, box)


def dashboard(cv: Canvas) -> None:
    """Metric cards. The first card carries the accent."""
    box = frame(cv, accent=False)
    stats = [(i, n) for i, n in cv.bag.take_all("stat") if isinstance(n, StatNode)][:6]
    rest = cv.bag.rest()
    if not stats:
        flow(cv, rest, box)
        return
    reserve = 150 if rest else 0
    area = Box(box.x, box.y, box.w, box.h - reserve)
    count = len(stats)
    if count <= 4:
        cells = Box(area.x, area.y, area.w, min(area.h, 400)).columns(count, 32)
    else:
        per_row = (count + 1) // 2
        cells = []
        for r, row in enumerate(area.rows(2, 32)):
            cells.extend(row.columns(per_row, 32)[: count - r * per_row if r else per_row])
    for n, ((index, stat), cell) in enumerate(zip(stats, cells)):
        components.stat_card(cv, index, stat, cell, emphasis=n == 0, max_size=112 if count <= 3 else 88)
    if rest:
        flow(cv, rest, Box(box.x, box.bottom - reserve + 32, 1400, reserve - 32))


def table(cv: Canvas) -> None:
    box = frame(cv)
    entry = cv.bag.take("table")
    rest = cv.bag.rest()
    if entry and isinstance(entry[1], TableNode):
        reserve = 90 if rest else 0
        components.table_block(cv, entry[0], entry[1], Box(box.x, box.y, box.w, box.h - reserve))
        if rest:
            flow(cv, rest, Box(box.x, box.bottom - reserve + 24, box.w, reserve - 24))
    else:
        flow(cv, rest, box)
