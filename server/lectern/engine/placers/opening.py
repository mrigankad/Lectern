"""Title, closing, section divider, agenda and the statement layouts (big idea, big number, quote)."""
from __future__ import annotations

from ...schema import BulletsNode, ItemsNode, QuoteNode, StatNode, TextNode
from .. import components
from .. import text as tx
from ..canvas import CONTENT_BOTTOM, CONTENT_W, GAP, H, MARGIN, Box, Canvas, W
from ..frame import eyebrow, flow, flow_rest, footer, frame


def _text(cv: Canvas, role: str) -> tuple[int, str] | None:
    entry = cv.bag.take("text", role)
    if entry and isinstance(entry[1], TextNode) and entry[1].value.strip():
        return entry[0], entry[1].value.strip()
    return None


def title(cv: Canvas) -> None:
    """Opening slide: the brand logo (or a small accent bar), a very large headline, a base line with the
    presenter details. A large empty accent tile read as a missing logo, so it is gone."""
    from ...schema import Element
    if cv.theme.logo:  # brand kit: the logo leads the title slide (place() skips its top-right copy)
        h = 96.0
        w = min(360.0, h * (cv.theme.logo_ratio or 1.0))
        cv.elements.append(Element(id="brand-logo", node=None, kind="image", x=MARGIN, y=MARGIN, w=w, h=h,
                                   src=cv.theme.logo, alt="Logo"))
    else:
        cv.rect(Box(MARGIN, 220, 56, 8), fill=cv.c.accent, radius=4)
    eyebrow(cv, y=272)
    box = Box(MARGIN, 328, 1560, 430)
    head = cv.fit(cv.slide.headline or "Untitled deck", box, 124, 64, node=cv.headline_index, weight=700,
                  line_height=1.06, max_lines=4)
    y = cv.bottom_of(head) + 36
    sub = _text(cv, "subhead")
    if sub and 880 - y >= 40:
        cv.fit(sub[1], Box(MARGIN, y, 1400, 880 - y), 40, 28, node=sub[0], color=cv.c.body, line_height=1.3)
    cv.rule(MARGIN, 920, CONTENT_W)
    caption = _text(cv, "caption")
    if caption:
        cv.fit(caption[1], Box(MARGIN, 948, CONTENT_W, 36), 24, tx.MIN_LABEL, node=caption[0], color=cv.c.body,
               max_lines=1)
    cv.bag.mark(cv.bag.rest())


def closing(cv: Canvas) -> None:
    """Last slide: the same bookend as the title, with the accent as a full-height band on the right."""
    band_w = 420
    cv.rect(Box(W - band_w, 0, band_w, H), fill=cv.c.accent)
    eyebrow(cv, y=272)
    width = W - band_w - 2 * MARGIN
    head = cv.fit(cv.slide.headline or "Thank you", Box(MARGIN, 328, width, 400), 112, 60,
                  node=cv.headline_index, weight=700, line_height=1.06, max_lines=4)
    y = cv.bottom_of(head) + 36
    sub = _text(cv, "subhead")
    if sub and 880 - y >= 40:
        cv.fit(sub[1], Box(MARGIN, y, width, 880 - y), 38, 28, node=sub[0], color=cv.c.body, line_height=1.3)
    cv.rule(MARGIN, 920, width)
    caption = _text(cv, "caption")
    if caption:
        cv.fit(caption[1], Box(MARGIN, 948, width, 36), 24, tx.MIN_LABEL, node=caption[0], color=cv.c.body,
               max_lines=1)
    cv.bag.mark(cv.bag.rest())


def section(cv: Canvas) -> None:
    """Section divider: the section number in white on a full-height accent panel."""
    panel = 620
    cv.rect(Box(0, 0, panel, H), fill=cv.c.accent)
    number = cv.context.section_number or cv.slide.index
    cv.text(f"{number:02d}", Box(MARGIN, 360, panel - 2 * MARGIN, 300), 240, weight=700, color=cv.c.on_accent,
            valign="middle", line_height=1.0)
    x = panel + MARGIN
    width = W - x - MARGIN
    eyebrow(cv, y=372, x=x)
    head = cv.fit(cv.slide.headline or "Section", Box(x, 420, width, 330), 92, 52, node=cv.headline_index,
                  weight=700, line_height=1.08, max_lines=4)
    sub = _text(cv, "subhead")
    if sub:
        y = cv.bottom_of(head) + 32
        cv.fit(sub[1], Box(x, y, width, max(40.0, 940 - y)), 34, 26, node=sub[0], color=cv.c.body,
               line_height=1.35)
    cv.bag.mark(cv.bag.rest())


def agenda(cv: Canvas) -> None:
    box = frame(cv)
    rows: list[tuple[int | None, str, str | None, str | None]] = []
    entry = cv.bag.take("items") or cv.bag.take("bullets")
    if entry:
        index, node = entry
        if isinstance(node, ItemsNode):
            rows = [(index, item.title, item.body, item.label) for item in node.items]
        elif isinstance(node, BulletsNode):
            rows = [(index, item, None, None) for item in node.items]
    main, side = _side(cv, box)
    components.numbered_rows(cv, rows[:10], main, max_row=120, title_max=36)
    flow_rest(cv, side)


def big_idea(cv: Canvas) -> None:
    """One statement in very large type with an accent bar under it."""
    eyebrow(cv)
    footer(cv)
    body = _text(cv, "body") or _text(cv, "subhead")
    caption = _text(cv, "caption")
    reserve = (150 if body else 0) + (50 if caption else 0)
    box = Box(MARGIN, 200, 1560, CONTENT_BOTTOM - 200 - reserve - 60)
    head = cv.fit(cv.slide.headline or "Untitled slide", box, 116, 56, node=cv.headline_index, weight=700,
                  line_height=1.08, max_lines=5)
    y = cv.bottom_of(head) + 36
    cv.rect(Box(MARGIN, y, 160, 12), fill=cv.c.accent, radius=6)
    y += 12 + 36
    if body:
        room = CONTENT_BOTTOM - y - (50 if caption else 0)
        element = cv.fit(body[1], Box(MARGIN, y, 1280, max(40.0, room)), 34, 26, node=body[0], color=cv.c.body,
                         line_height=1.4)
        y = cv.bottom_of(element) + 20
    if caption:
        cv.fit(caption[1], Box(MARGIN, CONTENT_BOTTOM - 30, CONTENT_W, 30), 22, tx.MIN_LABEL, node=caption[0],
               color=cv.c.body, max_lines=1)
    rest = cv.bag.rest()
    if rest and CONTENT_BOTTOM - y > 120:
        flow(cv, rest, Box(MARGIN, y, 1280, CONTENT_BOTTOM - y - (50 if caption else 0)))
    cv.bag.mark(cv.bag.rest())


def big_number(cv: Canvas) -> None:
    """One number on an accent block; the supporting text sits to its right."""
    box = frame(cv, accent=False, max_size=56)
    entry = cv.bag.take("stat")
    rest = cv.bag.rest()
    if not entry or not isinstance(entry[1], StatNode):
        flow(cv, rest, box)
        return
    index, stat = entry
    if not rest:
        components.hero_number(cv, index, stat, Box(box.x, box.y, box.w, min(box.h, 520)), wide=True)
        return
    block_w = 780
    components.hero_number(cv, index, stat, Box(box.x, box.y, block_w, box.h), wide=False)
    flow(cv, rest, Box(box.x + block_w + 72, box.y + 8, box.w - block_w - 72, box.h - 8))


def quote(cv: Canvas) -> None:
    box = frame(cv, accent=False, max_size=40, min_size=32)
    entry = cv.bag.take("quote")
    if entry and isinstance(entry[1], QuoteNode):
        rest = cv.bag.rest()
        reserve = 160 if rest else 0
        components.quote_block(cv, entry[0], entry[1], Box(box.x, box.y + 24, 1560, box.h - 24 - reserve), 64)
        if rest:
            flow(cv, rest, Box(box.x + 44, box.bottom - reserve + 24, 1400, reserve - 24))
    else:
        flow(cv, cv.bag.rest(), box)


def _side(cv: Canvas, box: Box) -> tuple[Box, Box | None]:
    if not cv.bag.rest():
        return box, None
    main_w = (box.w - GAP) * 0.66
    return Box(box.x, box.y, main_w, box.h), Box(box.x + main_w + GAP, box.y, box.w - main_w - GAP, box.h)
