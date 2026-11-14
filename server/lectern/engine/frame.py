"""The shared slide frame (accent marker, eyebrow, headline, footer) and the generic node flow."""
from __future__ import annotations

from ..schema import (BulletsNode, ChartNode, ImageNode, ItemsNode, Node, QuoteNode, StatNode, TableNode, TextNode)
from . import components
from . import text as tx
from .canvas import CONTENT_BOTTOM, CONTENT_W, GAP, MARGIN, Box, Canvas, W

HEADLINE_Y = 144
FLEX_MIN = 260


def footer(cv: Canvas) -> None:
    cv.rule(MARGIN, 984, CONTENT_W)
    cv.text(f"{cv.slide.index:02d}", Box(W - MARGIN - 200, 1002, 200, 28), tx.MIN_LABEL, weight=700,
            color=cv.c.body, align="right")


def eyebrow(cv: Canvas, y: float = 100, x: float = MARGIN, color: str | None = None) -> bool:
    found = cv.eyebrow()
    if not found:
        return False
    value, node = found
    cv.label(value, Box(x, y, W - MARGIN - x, 30), node=node, color=color)
    return True


def frame(cv: Canvas, *, accent: bool = True, max_size: int = 60, min_size: int = 40,
          width: float = 1520, with_footer: bool = True) -> Box:
    """Draw the standard top of a content slide. Returns the box left for content."""
    if accent:
        cv.rect(Box(MARGIN, 72, 56, 8), fill=cv.c.accent, radius=4)
    eyebrow(cv)
    headline = cv.slide.headline.strip() or "Untitled slide"
    two_lines = 2 * max_size * 1.12
    size = tx.fit_size(headline, width, two_lines, max_size, min_size, True, 1.12, max_lines=2)
    lines = tx.line_count(headline, size, width, True)
    height = min(lines, 3) * size * 1.12
    cv.text(headline, Box(MARGIN, HEADLINE_Y, width, height), size, node=cv.headline_index, weight=700,
            line_height=1.12)
    if with_footer:
        footer(cv)
    top = HEADLINE_Y + height + 56
    return Box(MARGIN, top, CONTENT_W, CONTENT_BOTTOM - top)


def split_side(cv: Canvas, box: Box, share: float = 0.68) -> tuple[Box, Box | None]:
    """Reserve a side column when the slide has nodes the layout does not draw itself."""
    if not cv.bag.rest():
        return box, None
    main_w = (box.w - GAP) * share
    return Box(box.x, box.y, main_w, box.h), Box(box.x + main_w + GAP, box.y, box.w - main_w - GAP, box.h)


def flow_rest(cv: Canvas, box: Box | None) -> None:
    rest = cv.bag.rest()
    if box is not None and rest:
        flow(cv, rest, box)


# ---------------------------------------------------------------- generic flow
def _natural_height(node: Node, width: float) -> float | None:
    """Height a node wants at its preferred size, or None when it takes whatever is left."""
    if isinstance(node, TextNode):
        size = {"subhead": 36, "caption": 22}.get(node.role, 32)
        return tx.text_height(node.value, size, width, False, 1.4)
    if isinstance(node, BulletsNode):
        return tx.bullets_height(node.items, 38, width)
    if isinstance(node, StatNode):
        return 230.0
    if isinstance(node, QuoteNode):
        return tx.text_height(node.text, 40, width - 44, True, 1.25) + (56 if node.attribution else 0)
    return None


def flow(cv: Canvas, entries: list[tuple[int, Node]], box: Box, gap: float = 32) -> None:
    """Stack nodes top to bottom inside the box. Text shrinks before anything overflows."""
    if not entries:
        return
    cv.bag.mark(entries)
    naturals = [_natural_height(node, box.w) for _, node in entries]
    available = box.h - gap * (len(entries) - 1)
    fixed = sum(n for n in naturals if n is not None)
    flexible = sum(1 for n in naturals if n is None)
    if flexible:
        each = max(FLEX_MIN, (available - fixed) / flexible)
        heights = [each if n is None else n for n in naturals]
    else:
        heights = [n or 0.0 for n in naturals]
    total = sum(heights)
    if total > available and total > 0:
        heights = [h * available / total for h in heights]
    y = box.y
    for (index, node), height in zip(entries, heights):
        draw_node(cv, index, node, Box(box.x, y, box.w, max(24.0, height)))
        y += height + gap


def draw_node(cv: Canvas, index: int, node: Node, box: Box) -> None:
    if isinstance(node, TextNode):
        if node.role == "subhead":
            cv.fit(node.value, box, 36, 26, node=index, color=cv.c.body, line_height=1.35)
        elif node.role == "caption":
            cv.fit(node.value, box, 22, tx.MIN_LABEL, node=index, color=cv.c.body, line_height=1.35)
        else:
            cv.fit(node.value, box, 32, tx.MIN_BODY, node=index, color=cv.c.body, line_height=1.4)
    elif isinstance(node, BulletsNode):
        cv.bullets(node.items, box, 38, tx.MIN_BODY, node=index)
    elif isinstance(node, StatNode):
        components.stat_card(cv, index, node, box, emphasis=False)
    elif isinstance(node, ChartNode):
        components.chart_block(cv, index, node, box)
    elif isinstance(node, TableNode):
        components.table_block(cv, index, node, box)
    elif isinstance(node, QuoteNode):
        components.quote_block(cv, index, node, box, max_size=44)
    elif isinstance(node, ItemsNode):
        if node.style == "steps":
            components.steps(cv, index, node.items, box)
        elif node.style == "timeline":
            components.timeline(cv, index, node.items, box)
        else:
            components.columns(cv, index, node.items, box)
    elif isinstance(node, ImageNode):
        components.image_block(cv, index, node, box)
