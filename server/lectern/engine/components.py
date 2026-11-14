"""Reusable pieces the layouts are assembled from. Every function draws inside the box it is given."""
from __future__ import annotations

import re

from ..schema import ChartNode, ImageNode, Item, QuoteNode, StatNode, TableNode
from . import text as tx
from .canvas import GAP, Box, Canvas

WHITE = "#FFFFFF"


# ---------------------------------------------------------------- numbers
def stat_card(cv: Canvas, index: int, stat: StatNode, box: Box, *, emphasis: bool, max_size: int = 112) -> None:
    """A metric card: big value, caption, source. `emphasis` puts it on the accent fill with white text."""
    fill = cv.c.accent if emphasis else cv.c.surface
    ink = cv.c.on_accent if emphasis else cv.c.ink
    soft = cv.c.on_accent if emphasis else cv.c.body
    cv.rect(box, fill=fill, radius=12)
    pad = 40 if box.w >= 360 else 24
    inner = box.inset(pad, min(pad, box.h * 0.14))
    source_h = 28 if stat.source else 0
    caption_h = min(inner.h * 0.38, 110) if stat.caption else 0
    value_h = max(40.0, inner.h - caption_h - source_h - (16 if caption_h else 0))
    size = _one_line_size(stat.value, inner.w, min(max_size, int(value_h / 1.05)), 44)
    value = cv.text(stat.value, Box(inner.x, inner.y, inner.w, min(value_h, size * 1.1)), size, node=index,
                    weight=700, color=ink, line_height=1.05)
    y = cv.bottom_of(value) + 12
    if stat.caption:
        room = max(30.0, inner.bottom - source_h - y)
        caption = cv.fit(stat.caption, Box(inner.x, y, inner.w, room), 28, tx.MIN_BODY, node=index, color=soft,
                         line_height=1.3)
        y = cv.bottom_of(caption) + 8
    if stat.source:
        cv.text(stat.source, Box(inner.x, inner.bottom - 26, inner.w, 26), tx.MIN_LABEL, node=index, color=soft,
                line_height=1.2)


def _one_line_size(value: str, width: float, max_size: int, min_size: int) -> int:
    size = max(min_size, max_size)
    while size > min_size and tx.text_width(value, size, True) > width:
        size -= 4
    return max(size, min_size)


def hero_number(cv: Canvas, index: int, stat: StatNode, box: Box, *, wide: bool) -> None:
    """The big-number block: one value on the accent fill, white text."""
    cv.rect(box, fill=cv.c.accent, radius=16)
    inner = box.inset(56, 48)
    if wide:
        left = Box(inner.x, inner.y, inner.w * 0.5, inner.h)
        right = Box(inner.x + inner.w * 0.5 + GAP, inner.y, inner.w * 0.5 - GAP, inner.h)
        size = _one_line_size(stat.value, left.w, min(260, int(left.h / 1.1)), 96)
        cv.text(stat.value, left, size, node=index, weight=700, color=cv.c.on_accent, valign="middle",
                line_height=1.0)
        if stat.caption:
            cv.fit(stat.caption, right.inset(0, right.h * 0.2), 44, 28, node=index, color=cv.c.on_accent,
                   line_height=1.25, valign="middle", tight=False)
        if stat.source:
            cv.text(stat.source, Box(right.x, inner.bottom - 26, right.w, 26), tx.MIN_LABEL, node=index,
                    color=cv.c.on_accent)
        return
    source_h = 34 if stat.source else 0
    caption_h = min(150.0, inner.h * 0.3) if stat.caption else 0
    value_h = inner.h - caption_h - source_h
    size = _one_line_size(stat.value, inner.w, min(240, int(value_h / 1.05)), 96)
    cv.text(stat.value, Box(inner.x, inner.y, inner.w, value_h), size, node=index, weight=700,
            color=cv.c.on_accent, valign="middle", line_height=1.0)
    if stat.caption:
        cv.fit(stat.caption, Box(inner.x, inner.y + value_h, inner.w, caption_h), 34, tx.MIN_BODY, node=index,
               color=cv.c.on_accent, line_height=1.25)
    if stat.source:
        cv.text(stat.source, Box(inner.x, inner.bottom - 26, inner.w, 26), tx.MIN_LABEL, node=index,
                color=cv.c.on_accent)


# ---------------------------------------------------------------- data
def chart_block(cv: Canvas, index: int, chart: ChartNode, box: Box) -> None:
    if chart.title:
        cv.text(chart.title, Box(box.x, box.y, box.w, 34), 24, node=index, weight=700, line_height=1.2)
        box = box.below(box.y + 50)
    cv.chart(chart, box, index)


def table_metrics(table: TableNode, box: Box) -> tuple[int, float, float]:
    """Font size, row height and total height for a table drawn in the box."""
    rows = len(table.rows) + 1
    cols = max(1, len(table.columns))
    cell_w = box.w / cols - 32
    for size in (28, 26, 24, 22, 20):
        row_h = 0.0
        for row in [table.columns, *table.rows]:
            lines = max((tx.line_count(str(cell), size, cell_w, False) for cell in row), default=1)
            row_h = max(row_h, lines * size * 1.25 + 28)
        if row_h * rows <= box.h or size == 20:
            return size, row_h, row_h * rows
    return 20, 60.0, 60.0 * rows


def table_block(cv: Canvas, index: int, table: TableNode, box: Box) -> None:
    size, _row_h, total = table_metrics(table, box)
    cv.table(table, Box(box.x, box.y, box.w, min(box.h, total)), index, size)


def quote_block(cv: Canvas, index: int, quote: QuoteNode, box: Box, max_size: int = 60) -> None:
    attribution_h = 52 if quote.attribution else 0
    text_box = Box(box.x + 44, box.y, box.w - 44, max(40.0, box.h - attribution_h))
    element = cv.fit(quote.text, text_box, max_size, 28, node=index, weight=700, line_height=1.25)
    cv.rect(Box(box.x, box.y + 4, 10, max(24.0, element.h - 8)), fill=cv.c.accent, radius=5)
    if quote.attribution:
        cv.text(quote.attribution, Box(text_box.x, cv.bottom_of(element) + 20, text_box.w, 32), 26, node=index,
                color=cv.c.body, line_height=1.2)


def image_block(cv: Canvas, index: int, image: ImageNode, box: Box) -> None:
    if image.src:
        cv.image(image.src, image.alt, box, index)
        return
    cv.rect(box, fill=cv.c.surface, stroke=cv.c.line, stroke_width=2, radius=12)
    caption = image.alt or image.prompt or "Image"
    cv.fit(caption, box.inset(32), 26, tx.MIN_BODY, node=index, color=cv.c.body, align="center", valign="middle",
           tight=False)


# ---------------------------------------------------------------- items
def _grid(count: int, box: Box, max_per_row: int, row_gap: float = 40) -> list[Box]:
    if count <= max_per_row:
        return box.columns(count)
    per_row = (count + 1) // 2
    cells: list[Box] = []
    for r, row in enumerate(box.rows(2, row_gap)):
        cells.extend(row.columns(per_row)[: count - r * per_row if r else per_row])
    return cells[:count]


def _title(cv: Canvas, index: int, item: Item, box: Box, *, title_max: int = 40, label: bool = True) -> float:
    """Label and title from the top of the box. Returns the y where the title ends."""
    y = box.y
    if label and item.label:
        cv.label(item.label, Box(box.x, y, box.w, 28), node=index)
        y += 40
    title = cv.fit(item.title, Box(box.x, y, box.w, max(40.0, min(box.h * 0.45, 3 * title_max * 1.2))), title_max,
                   26, node=index, weight=700, line_height=1.2, max_lines=3)
    return cv.bottom_of(title)


def _body(cv: Canvas, index: int, item: Item, box: Box, y: float, body_max: int = 30) -> None:
    if item.body and item.body.strip() and box.bottom - y >= 30:
        cv.fit(item.body, Box(box.x, y, box.w, box.bottom - y), body_max, tx.MIN_BODY, node=index,
               color=cv.c.body, line_height=1.4)


def _title_body(cv: Canvas, index: int, item: Item, box: Box, *, title_max: int = 40, body_max: int = 30,
                label: bool = True) -> None:
    """Label, title and body stacked from the top of the box."""
    bottom = _title(cv, index, item, box, title_max=title_max, label=label)
    _body(cv, index, item, box, bottom + 16, body_max)


def _titles_then_bodies(cv: Canvas, index: int, items: list[Item], cells: list[Box], *, title_max: int,
                        body_max: int, label: bool = True) -> None:
    """Draw a row of title/body cells so that every body in a row starts on the same line."""
    bottoms = [_title(cv, index, item, cell, title_max=title_max, label=label) for item, cell in zip(items, cells)]
    for item, cell in zip(items, cells):
        row_bottom = max(b for b, other in zip(bottoms, cells) if other.y == cell.y)
        _body(cv, index, item, cell, row_bottom + 16, body_max)


def columns(cv: Canvas, index: int, items: list[Item], box: Box, *, numbered: bool = False,
            divider: bool = False) -> None:
    """Equal columns, each under a short ink rule."""
    items = items[:8]
    if not items:
        return
    cells = _grid(len(items), box, 4)
    inner: list[Box] = []
    for n, (item, cell) in enumerate(zip(items, cells)):
        cv.rect(Box(cell.x, cell.y, 48, 4), fill=cv.c.ink)
        y = cell.y + 28
        if numbered and not item.label:
            cv.label(f"{n + 1:02d}", Box(cell.x, y, cell.w, 28), node=None)
            y += 40
        inner.append(cell.below(y))
        if divider and n < len(cells) - 1 and cells[n + 1].y == cell.y:
            cv.vrule(cell.right + GAP / 2 - 1, cell.y, cell.h)
    roomy = len(items) <= 3
    _titles_then_bodies(cv, index, items, inner, title_max=44 if roomy else 36, body_max=32 if roomy else 28)


def steps(cv: Canvas, index: int, items: list[Item], box: Box) -> None:
    """Numbered steps left to right, joined by a rule."""
    items = items[:6]
    if not items:
        return
    cells = _grid(len(items), box, 5)
    badge = 64
    for n, (item, cell) in enumerate(zip(items, cells)):
        cv.rect(Box(cell.x, cell.y, badge, badge), fill=cv.c.ink, radius=12)
        cv.text(str(n + 1), Box(cell.x, cell.y, badge, badge), 28, weight=700, color=WHITE, align="center",
                valign="middle", line_height=1.0)
        if n < len(cells) - 1 and cells[n + 1].y == cell.y:
            cv.rule(cell.x + badge + 16, cell.y + badge / 2 - 1, cell.w + GAP - badge - 32)
    # A label that only repeats the badge number ("1", "01", "Step 1") would print the number twice.
    shown = [item.model_copy(update={"label": None}) if _is_step_number(item.label, n + 1) else item
             for n, item in enumerate(items)]
    _titles_then_bodies(cv, index, shown, [c.below(c.y + badge + 32) for c in cells], title_max=36, body_max=28)


def _is_step_number(label: str | None, n: int) -> bool:
    text = (label or "").strip().lower().removeprefix("step").strip().rstrip(".")
    return bool(text) and text.isdigit() and int(text) == n


def timeline(cv: Canvas, index: int, items: list[Item], box: Box) -> None:
    """Milestones on a horizontal axis; the label (date or phase) sits above the axis."""
    items = items[:6]
    if not items:
        return
    cells = box.columns(len(items), 40)
    axis_y = box.y + 56
    cv.rule(box.x, axis_y - 1, box.w, color=cv.c.ink)
    for n, (item, cell) in enumerate(zip(items, cells)):
        cv.label(item.label or f"Step {n + 1}", Box(cell.x, box.y, cell.w, 28), node=index, color=cv.c.ink)
        cv.rect(Box(cell.x, axis_y - 9, 18, 18), fill=cv.c.accent if n == len(items) - 1 else cv.c.ink, radius=9)
    _titles_then_bodies(cv, index, items, [c.below(axis_y + 40) for c in cells], title_max=34, body_max=28,
                        label=False)


def diagram(cv: Canvas, index: int, items: list[Item], box: Box) -> None:
    """Connected boxes in flow order: a simple native architecture diagram."""
    items = items[:6]
    if not items:
        return
    count = len(items)
    per_row = count if count <= 4 else (count + 1) // 2
    rows = 1 if count <= 4 else 2
    gap = 72
    row_gap = 56
    height = min(340.0, (box.h - row_gap * (rows - 1)) / rows)
    width = (box.w - gap * (per_row - 1)) / per_row
    for n, item in enumerate(items):
        r, c = divmod(n, per_row)
        cell = Box(box.x + c * (width + gap), box.y + r * (height + row_gap), width, height)
        cv.rect(cell, fill=cv.c.surface, stroke=cv.c.ink, stroke_width=2, radius=12)
        _title_body(cv, index, item, cell.inset(28, 28), title_max=30, body_max=26)
        if c < per_row - 1 and n < count - 1:
            cv.rule(cell.right + 8, cell.y + height / 2 - 1, gap - 16, color=cv.c.ink, thickness=3)
            cv.rect(Box(cell.right + gap - 20, cell.y + height / 2 - 6, 12, 12), fill=cv.c.ink, radius=6)


def people(cv: Canvas, index: int, items: list[Item], box: Box) -> None:
    """Team cards: an initials tile, the name, the role and a short bio."""
    items = items[:6]
    if not items:
        return
    cells = _grid(len(items), box, 4)
    tile = 96
    for item, cell in zip(items, cells):
        cv.rect(Box(cell.x, cell.y, tile, tile), fill=cv.c.ink, radius=12)
        cv.text(_initials(item.title), Box(cell.x, cell.y, tile, tile), 34, weight=700, color=WHITE,
                align="center", valign="middle", line_height=1.0)
    _titles_then_bodies(cv, index, [_swap_label_under_title(i) for i in items],
                        [c.below(c.y + tile + 28) for c in cells], title_max=32, body_max=26, label=False)


def _swap_label_under_title(item: Item) -> Item:
    if not item.label:
        return item
    body = f"{item.label}\n{item.body}" if item.body else item.label
    return Item(title=item.title, body=body)


def _initials(name: str) -> str:
    words = [w for w in re.split(r"[\s\-]+", name.strip()) if w and w[0].isalnum()]
    return "".join(w[0].upper() for w in words[:2]) or "?"


def numbered_rows(cv: Canvas, rows: list[tuple[int | None, str, str | None, str | None]], box: Box, *,
                  badge: bool = False, max_row: float = 132, title_max: int = 36) -> None:
    """Rows separated by hairlines: number, title, optional body, optional right-hand label.

    Each row is (node index, title, body, label).
    """
    if not rows:
        return
    two_cols = len(rows) > 5
    groups = [rows[: (len(rows) + 1) // 2], rows[(len(rows) + 1) // 2:]] if two_cols else [rows]
    areas = box.columns(2, 96) if two_cols else [Box(box.x, box.y, min(box.w, 1440), box.h)]
    counter = 0
    for group, area in zip(groups, areas):
        row_h = min(max_row, area.h / max(1, len(group)))
        has_label = any(label for *_rest, label in group)
        label_w = min(380.0, area.w * 0.3) if has_label else 0.0
        for n, (node, title, body, label) in enumerate(group):
            counter += 1
            y = area.y + n * row_h
            if n:
                cv.rule(area.x, y, area.w)
            num_box = Box(area.x, y + (row_h - 56) / 2, 56, 56)
            if badge:
                cv.rect(num_box, fill=cv.c.ink, radius=10)
                cv.text(str(counter), num_box, 26, weight=700, color=WHITE, align="center", valign="middle",
                        line_height=1.0)
            else:
                cv.text(f"{counter:02d}", Box(area.x, y, 72, row_h), 28, weight=700, color=cv.c.accent,
                        valign="middle", line_height=1.0)
            text_x = area.x + 96
            text_w = area.w - 96 - (label_w + 32 if label_w else 0)
            inner_h = row_h - 24
            if body and body.strip():
                title_h = inner_h * 0.5
                cv.fit(title, Box(text_x, y + 12, text_w, title_h), min(title_max, 32), tx.MIN_BODY, node=node,
                       weight=700, valign="bottom", line_height=1.15, tight=False, max_lines=2)
                cv.fit(body, Box(text_x, y + 12 + title_h + 4, text_w, inner_h - title_h - 4), 26, tx.MIN_BODY,
                       node=node, color=cv.c.body, line_height=1.25, tight=False, max_lines=2)
            else:
                cv.fit(title, Box(text_x, y + 12, text_w, inner_h), title_max, tx.MIN_BODY, node=node,
                       weight=700 if badge or title_max >= 36 else 400, valign="middle", line_height=1.2,
                       tight=False)
            if label and label_w:
                cv.label(label, Box(area.right - label_w, y, label_w, row_h), node=node, align="right",
                         valign="middle", uppercase=False)
