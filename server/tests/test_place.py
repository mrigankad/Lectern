"""Placement invariants: everything stays on the canvas, and no text drops under the minimum size."""
from __future__ import annotations

import pytest

from lectern.engine import text as tx
from lectern.engine.lint import background_of, contrast_ratio
from lectern.engine.place import place, place_deck
from lectern.layouts import LAYOUT_IDS, registry
from lectern.schema import ImageNode, RenderedSlide, Slide, TextNode, Theme

from . import samples


def assert_invariants(rendered: RenderedSlide) -> None:
    assert rendered.width == 1920 and rendered.height == 1080
    ids = [e.id for e in rendered.elements]
    assert len(ids) == len(set(ids))
    for e in rendered.elements:
        where = f"slide {rendered.index} element {e.id} ({e.kind})"
        assert e.w > 0 and e.h > 0, where
        assert e.x >= 0 and e.y >= 0, where
        assert e.x + e.w <= 1920 and e.y + e.h <= 1080, where
        if e.kind == "text":
            assert e.style is not None and e.style.font_size is not None, where
            assert e.style.font_size >= tx.MIN_LABEL, where
            if e.bullets:
                assert e.style.font_size >= tx.MIN_BODY, where
            assert (e.text or e.bullets), where


def test_registry_has_all_21_layouts() -> None:
    assert len(LAYOUT_IDS) == 21 and set(registry()) == set(LAYOUT_IDS)
    assert {s.layout for s in samples.all_layouts()} == set(LAYOUT_IDS)


@pytest.mark.parametrize("slide", samples.all_layouts(), ids=lambda s: s.layout)
def test_sample_layout_is_inside_canvas(slide: Slide) -> None:
    rendered = place(slide, Theme())
    assert_invariants(rendered)
    used = {e.node for e in rendered.elements if e.node is not None}
    for index, node in enumerate(slide.nodes):
        if isinstance(node, TextNode) and node.role == "eyebrow":
            continue
        assert index in used, f"{slide.layout}: node {index} ({node.type}) was not placed"


@pytest.mark.parametrize("slide", samples.stress_layouts(), ids=lambda s: s.layout)
def test_overloaded_layout_stays_inside_canvas(slide: Slide) -> None:
    assert_invariants(place(slide, Theme()))


def test_empty_and_odd_slides_still_place() -> None:
    for layout in LAYOUT_IDS:
        bare = Slide(id="x", index=3, headline="", layout=layout, nodes=[])  # type: ignore[arg-type]
        assert_invariants(place(bare, Theme()))
        with_image = Slide(id="y", index=4, headline="A slide with an image and nothing else", layout=layout,  # type: ignore[arg-type]
                           nodes=[ImageNode(alt="Team photo", prompt="a team at work")])
        assert_invariants(place(with_image, Theme()))


def test_long_text_steps_down_instead_of_overflowing() -> None:
    short = samples.slide(1, "bullets", "Short", [samples.BulletsNode(items=["One", "Two"])])
    long = samples.slide(1, "bullets", "Short", [samples.BulletsNode(items=[samples.LONG] * 5)])
    size = lambda s: next(e for e in place(s).elements if e.bullets).style.font_size  # noqa: E731
    assert size(long) < size(short)
    assert size(long) >= tx.MIN_BODY


def test_placement_is_deterministic() -> None:
    slides = samples.all_layouts()
    assert [r.model_dump() for r in place_deck(slides)] == [r.model_dump() for r in place_deck(slides)]


def test_default_theme_house_style() -> None:
    """Accent is the house blue; text on an accent fill is white; nothing is chrome yellow."""
    theme = Theme()
    assert theme.colors.accent == "#2563EB" and theme.colors.on_accent == "#FFFFFF"
    assert theme.chart_colors[0] == "#2563EB"
    accent_blocks = 0
    for rendered in place_deck(samples.all_layouts(), theme):
        for e in rendered.elements:
            style = e.style
            assert "FFC400" not in str(e.model_dump()).upper()
            if e.kind == "text" and style and style.color:
                background = background_of(e, rendered)
                assert contrast_ratio(style.color, background) >= 4.5, (rendered.index, e.text, background)
                if background.upper() == theme.colors.accent:
                    accent_blocks += 1
                    assert style.color.upper() == "#FFFFFF"
    assert accent_blocks >= 5


def test_section_numbers_follow_deck_order() -> None:
    first = samples.slide(2, "section", "The risk", [])
    second = samples.slide(5, "section", "The plan", [])
    rendered = place_deck([samples.all_layouts()[0], first, samples.all_layouts()[4], second])
    numbers = [next(e.text for e in r.elements if e.kind == "text" and e.style.font_size >= 200)
               for r in (rendered[1], rendered[3])]
    assert numbers == ["01", "02"]
