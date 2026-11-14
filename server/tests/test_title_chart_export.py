"""Regression: the title slide has no big empty accent tile; line chart labels sit above the markers."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.chart import XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE_TYPE

from lectern.engine.place import place_deck
from lectern.export.pptx import EMU_PER_PX, build_pptx
from lectern.schema import ChartNode, Series, Theme

from . import samples


def _logo_uri() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "#1D4ED8").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_title_slide_uses_small_accent_bar(tmp_path: Path) -> None:
    slide = samples.all_layouts()[0]
    rendered = place_deck([slide], Theme())
    rects = [e for e in rendered[0].elements if e.kind == "rect"]
    assert rects and all(e.h <= 12 for e in rects), "no big accent tile on the title slide"
    path = tmp_path / "title.pptx"
    build_pptx([slide], rendered, Theme(), path)
    for shape in Presentation(str(path)).slides[0].shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            assert shape.height <= 12 * EMU_PER_PX


def test_title_slide_shows_brand_logo_once(tmp_path: Path) -> None:
    slide = samples.all_layouts()[0]
    theme = Theme(logo=_logo_uri(), logo_ratio=2.0)
    rendered = place_deck([slide], theme)
    logos = [e for e in rendered[0].elements if e.id == "brand-logo"]
    assert len(logos) == 1 and logos[0].x < 200, "logo leads the title slide, top left"
    assert not any(e.kind == "rect" and e.h > 12 for e in rendered[0].elements)
    path = tmp_path / "brand.pptx"
    build_pptx([slide], rendered, theme, path)
    pictures = [s for s in Presentation(str(path)).slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1


def test_line_chart_labels_sit_above(tmp_path: Path) -> None:
    slide = samples.slide(2, "chart", "Revenue keeps climbing", [
        ChartNode(kind="line", categories=["Q1", "Q2", "Q3", "Q4"],
                  series=[Series(name="Revenue", values=[1.2, 1.8, 2.4, 3.2])], unit="$")])
    rendered = place_deck([slide], Theme())
    path = tmp_path / "line.pptx"
    build_pptx([slide], rendered, Theme(), path)
    chart = next(s for s in Presentation(str(path)).slides[0].shapes if s.has_chart).chart
    plot = chart.plots[0]
    assert plot.has_data_labels
    assert plot.data_labels.position == XL_LABEL_POSITION.ABOVE
