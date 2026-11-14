"""The drawing surface used by the placers: boxes in canvas px, elements out."""
from __future__ import annotations

from dataclasses import dataclass

from ..schema import (ChartNode, ChartSpec, Element, Node, Slide, Style, TableNode, TableSpec, TextNode, Theme)
from . import text as tx

W = 1920
H = 1080
MARGIN = 96
CONTENT_W = W - 2 * MARGIN
CONTENT_BOTTOM = 948
GAP = 48


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def inset(self, dx: float, dy: float | None = None) -> "Box":
        dy = dx if dy is None else dy
        return Box(self.x + dx, self.y + dy, max(1.0, self.w - 2 * dx), max(1.0, self.h - 2 * dy))

    def columns(self, count: int, gap: float = GAP) -> list["Box"]:
        width = (self.w - gap * (count - 1)) / count
        return [Box(self.x + i * (width + gap), self.y, width, self.h) for i in range(count)]

    def rows(self, count: int, gap: float = 0.0) -> list["Box"]:
        height = (self.h - gap * (count - 1)) / count
        return [Box(self.x, self.y + i * (height + gap), self.w, height) for i in range(count)]

    def below(self, y: float) -> "Box":
        """The part of the box from absolute y downward."""
        y = min(max(y, self.y), self.bottom - 1)
        return Box(self.x, y, self.w, self.bottom - y)

    def top(self, height: float) -> "Box":
        return Box(self.x, self.y, self.w, min(height, self.h))


@dataclass(frozen=True)
class PlaceContext:
    """Deck-level facts a single slide cannot know."""
    section_number: int | None = None
    total: int | None = None


class Bag:
    """The slide's nodes, with a record of which ones a placer has drawn."""

    def __init__(self, nodes: list[Node]) -> None:
        self.entries: list[tuple[int, Node]] = list(enumerate(nodes))
        self.used: set[int] = set()

    def take(self, node_type: str, role: str | None = None) -> tuple[int, Node] | None:
        for index, node in self.entries:
            if index in self.used or node.type != node_type:
                continue
            if role is not None and not (isinstance(node, TextNode) and node.role == role):
                continue
            self.used.add(index)
            return index, node
        return None

    def take_all(self, node_type: str) -> list[tuple[int, Node]]:
        found = []
        while (entry := self.take(node_type)) is not None:
            found.append(entry)
        return found

    def rest(self) -> list[tuple[int, Node]]:
        """Undrawn nodes, in order. Empty text nodes are skipped."""
        out = []
        for index, node in self.entries:
            if index in self.used:
                continue
            if isinstance(node, TextNode) and (node.role in {"headline", "eyebrow"} or not node.value.strip()):
                continue
            out.append((index, node))
        return out

    def mark(self, entries: list[tuple[int, Node]]) -> None:
        self.used.update(index for index, _ in entries)


class Canvas:
    def __init__(self, slide: Slide, theme: Theme, context: PlaceContext | None = None) -> None:
        self.slide = slide
        self.theme = theme
        self.c = theme.colors
        self.context = context or PlaceContext()
        self.bag = Bag(slide.nodes)
        self.elements: list[Element] = []

    # ------------------------------------------------------------ primitives
    def _add(self, kind: str, box: Box, node: int | None, **fields: object) -> Element:
        x = min(max(0.0, box.x), W - 1)
        y = min(max(0.0, box.y), H - 1)
        element = Element(
            id=f"{self.slide.id}-e{len(self.elements) + 1}", node=node, kind=kind,  # type: ignore[arg-type]
            x=round(x), y=round(y), w=round(max(1.0, min(box.w, W - x))), h=round(max(1.0, min(box.h, H - y))),
            **fields,  # type: ignore[arg-type]
        )
        self.elements.append(element)
        return element

    def rect(self, box: Box, fill: str | None = None, stroke: str | None = None, stroke_width: float | None = None,
             radius: float | None = None, node: int | None = None) -> Element:
        style = Style(fill=fill, stroke=stroke, stroke_width=stroke_width if stroke else None, radius=radius)
        return self._add("rect", box, node, style=style)

    def rule(self, x: float, y: float, w: float, color: str | None = None, thickness: float = 2) -> Element:
        return self.rect(Box(x, y, w, thickness), fill=color or self.c.line)

    def vrule(self, x: float, y: float, h: float, color: str | None = None, thickness: float = 2) -> Element:
        return self.rect(Box(x, y, thickness, h), fill=color or self.c.line)

    def text(self, value: str, box: Box, size: float, *, node: int | None = None, weight: int = 400,
             color: str | None = None, align: str = "left", valign: str = "top", line_height: float = 1.25,
             uppercase: bool = False, letter_spacing: float | None = None) -> Element:
        style = Style(font_size=size, font_weight=weight, color=color or self.c.ink,  # type: ignore[arg-type]
                      align=align, valign=valign, line_height=line_height,  # type: ignore[arg-type]
                      uppercase=True if uppercase else None, letter_spacing=letter_spacing)
        return self._add("text", box, node, text=value, style=style)

    def fit(self, value: str, box: Box, max_size: int, min_size: int, *, node: int | None = None, weight: int = 400,
            color: str | None = None, align: str = "left", valign: str = "top", line_height: float = 1.25,
            max_lines: int | None = None, tight: bool = True) -> Element:
        """Text at the largest size that fits the box. With `tight`, the element is trimmed to the text."""
        bold = weight >= 700
        size = tx.fit_size(value, box.w, box.h, max_size, min_size, bold, line_height, max_lines)
        needed = tx.text_height(value, size, box.w, bold, line_height)
        if tight and valign == "top":
            box = Box(box.x, box.y, box.w, min(box.h, needed))
        return self.text(value, box, size, node=node, weight=weight, color=color, align=align, valign=valign,
                         line_height=line_height)

    def label(self, value: str, box: Box, *, node: int | None = None, color: str | None = None, size: int = 22,
              align: str = "left", valign: str = "top", uppercase: bool = True) -> Element:
        """Small bold caps label (eyebrows, dates, roles)."""
        return self.text(value, box, size, node=node, weight=700, color=color or self.c.body, align=align,
                         valign=valign, line_height=1.2, uppercase=uppercase,
                         letter_spacing=round(size * 0.08, 1) if uppercase else None)

    def bullets(self, items: list[str], box: Box, max_size: int = 34, min_size: int = tx.MIN_BODY, *,
                node: int | None = None, color: str | None = None, line_height: float = 1.3) -> Element:
        size = tx.fit_bullets(items, box.w, box.h, max_size, min_size, line_height)
        needed = tx.bullets_height(items, size, box.w, line_height)
        style = Style(font_size=size, font_weight=400, color=color or self.c.ink, align="left", valign="top",
                      line_height=line_height)
        return self._add("text", Box(box.x, box.y, box.w, min(box.h, needed)), node, bullets=list(items), style=style)

    def chart(self, chart: ChartNode, box: Box, node: int | None) -> Element:
        spec = ChartSpec(kind=chart.kind, categories=chart.categories, series=chart.series,
                         colors=_cycle(self.theme.chart_colors, max(len(chart.series), len(chart.categories))),
                         unit=chart.unit)
        return self._add("chart", box, node, chart=spec,
                         style=Style(font_size=22, color=self.c.body))

    def table(self, table: TableNode, box: Box, node: int | None, size: int) -> Element:
        return self._add("table", box, node, table=TableSpec(columns=table.columns, rows=table.rows),
                         style=Style(font_size=size, color=self.c.ink, fill=self.c.surface, stroke=self.c.line))

    def image(self, src: str, alt: str, box: Box, node: int | None) -> Element:
        return self._add("image", box, node, src=src, alt=alt)

    # ------------------------------------------------------------ helpers
    @property
    def headline_index(self) -> int | None:
        for index, node in self.bag.entries:
            if isinstance(node, TextNode) and node.role == "headline":
                return index
        return None

    def eyebrow(self) -> tuple[str, int | None] | None:
        for index, node in self.bag.entries:
            if isinstance(node, TextNode) and node.role == "eyebrow" and node.value.strip():
                return node.value.strip(), index
        if self.slide.section and self.slide.section.strip():
            return self.slide.section.strip(), None
        return None

    def bottom_of(self, element: Element) -> float:
        return element.y + element.h


def _cycle(colors: list[str], count: int) -> list[str]:
    if not colors:
        colors = ["#16181D"]
    return [colors[i % len(colors)] for i in range(max(1, count))]
