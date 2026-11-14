"""Deterministic placement: Slide + Theme -> RenderedSlide (absolute boxes on a 1920x1080 canvas)."""
from __future__ import annotations

from ..schema import RenderedSlide, Slide, Theme
from .canvas import Canvas, PlaceContext
from .placers import PLACERS


def place(slide: Slide, theme: Theme | None = None, context: PlaceContext | None = None) -> RenderedSlide:
    theme = theme or Theme()
    canvas = Canvas(slide, theme, context)
    PLACERS.get(slide.layout, PLACERS["bullets"])(canvas)
    if theme.logo and not any(e.id == "brand-logo" for e in canvas.elements):  # brand kit logo (U09), top right on every slide
        from ..schema import Element
        h = 56.0
        w = min(240.0, h * (theme.logo_ratio or 1.0))
        canvas.elements.append(Element(id="brand-logo", node=None, kind="image", x=1920 - 72 - w, y=36, w=w, h=h,
                                       src=theme.logo, alt="Logo"))
    return RenderedSlide(id=slide.id, index=slide.index, background=theme.colors.bg, elements=canvas.elements)


def place_deck(slides: list[Slide], theme: Theme | None = None) -> list[RenderedSlide]:
    """Place every slide, numbering section dividers in deck order."""
    rendered = []
    section_number = 0
    for slide in slides:
        if slide.layout == "section":
            section_number += 1
        rendered.append(place(slide, theme, PlaceContext(section_number=section_number or None,
                                                         total=len(slides))))
    return rendered


def context_for(slides: list[Slide], slide: Slide) -> PlaceContext:
    number = sum(1 for s in slides if s.layout == "section" and s.index <= slide.index)
    return PlaceContext(section_number=number or None, total=len(slides))
