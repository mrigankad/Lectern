"""The exported .pptx, re-opened: charts are charts, tables are tables, text is text, no pictures."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Pt

from lectern.engine.place import place_deck
from lectern.export.pptx import build_pptx
from lectern.export.report import build_report
from lectern.schema import ChartNode, ImageNode, Series, Slide, Theme

from . import samples


def export(slides: list[Slide], path: Path, include_notes: bool = True):  # type: ignore[no-untyped-def]
    rendered = place_deck(slides, Theme())
    build_pptx(slides, rendered, Theme(), path, include_notes=include_notes, title="Test deck")
    return rendered, Presentation(str(path))


def test_native_objects_and_no_pictures(tmp_path: Path) -> None:
    slides = samples.all_layouts()
    rendered, prs = export(slides, tmp_path / "deck.pptx")
    assert prs.slide_width == 12192000 and prs.slide_height == 6858000      # 13.333in x 7.5in
    assert len(prs.slides) == len(slides)

    charts = tables = pictures = text_boxes = 0
    for page, drawn in zip(prs.slides, rendered):
        assert len(page.shapes) == len(drawn.elements)
        for shape in page.shapes:
            assert shape.left >= 0 and shape.top >= 0
            assert shape.left + shape.width <= prs.slide_width and shape.top + shape.height <= prs.slide_height
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                pictures += 1
            elif shape.has_chart:
                charts += 1
            elif shape.has_table:
                tables += 1
            elif shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
                text_boxes += 1
    assert pictures == 0
    assert charts == sum(1 for s in slides for n in s.nodes if n.type == "chart") == 1
    assert tables == sum(1 for s in slides for n in s.nodes if n.type == "table") == 2
    assert text_boxes == sum(1 for r in rendered for e in r.elements if e.kind == "text")


def test_chart_carries_the_slide_data(tmp_path: Path) -> None:
    slide = samples.all_layouts()[9]
    _rendered, prs = export([slide], tmp_path / "chart.pptx")
    frame = next(shape for shape in prs.slides[0].shapes if shape.has_chart)
    chart = frame.chart
    assert chart.chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED
    plot = chart.plots[0]
    assert list(plot.categories) == ["Q2", "Q3"]
    assert [(s.name, list(s.values)) for s in plot.series] == [("Monthly logo churn", [2.6, 4.1])]
    assert frame.chart.part.chart_workbook.xlsx_part is not None        # the editable data sheet is embedded


def test_every_chart_kind_exports_as_a_chart(tmp_path: Path) -> None:
    kinds = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS,
             "area": XL_CHART_TYPE.AREA, "pie": XL_CHART_TYPE.PIE}
    slides = [samples.slide(i + 1, "chart", "Revenue grew every quarter", [ChartNode(
        kind=kind, categories=["Q1", "Q2", "Q3"],  # type: ignore[arg-type]
        series=[Series(name="Revenue", values=[1.0, 2.0, 3.5])], unit="$")]) for i, kind in enumerate(kinds)]
    _rendered, prs = export(slides, tmp_path / "kinds.pptx")
    found = [next(s for s in page.shapes if s.has_chart).chart.chart_type for page in prs.slides]
    assert found == list(kinds.values())


def test_table_cells_and_text_are_live(tmp_path: Path) -> None:
    slides = samples.all_layouts()
    _rendered, prs = export(slides, tmp_path / "deck.pptx")
    table = next(shape for shape in prs.slides[11].shapes if shape.has_table).table
    assert [cell.text for cell in table.rows[0].cells] == ["Option", "Cost", "Churn impact", "Time to effect"]
    assert table.cell(2, 1).text == "$1.2M" and len(table.rows) == 4

    title_texts = [s.text_frame.text for s in prs.slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX]
    assert "Q3 board review" in title_texts
    headline = next(s for s in prs.slides[0].shapes if s.has_text_frame and s.text_frame.text == "Q3 board review")
    run = headline.text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Urbanist" and run.font.bold is True
    assert run.font.size == Pt(next(e for e in _rendered[0].elements if e.text == "Q3 board review").style.font_size / 2)

    bullets = next(s for s in prs.slides[4].shapes if s.has_text_frame and len(s.text_frame.paragraphs) == 4)
    assert bullets.text_frame.paragraphs[0].text == "Revenue is up 34% on last year"
    assert "buChar" in bullets.text_frame.paragraphs[0]._p.xml


def test_notes(tmp_path: Path) -> None:
    slides = samples.all_layouts()[:3]
    _r, with_notes = export(slides, tmp_path / "a.pptx", include_notes=True)
    assert all(page.has_notes_slide and page.notes_slide.notes_text_frame.text == slides[0].notes
               for page in with_notes.slides)
    _r, without = export(slides, tmp_path / "b.pptx", include_notes=False)
    assert not any(page.has_notes_slide for page in without.slides)


def test_report_counts_match_the_file(tmp_path: Path) -> None:
    slides = samples.all_layouts()
    path = tmp_path / "deck.pptx"
    rendered, prs = export(slides, path)
    report = build_report(path, rendered, notes_expected=len(slides))
    assert report.total_objects == sum(len(page.shapes) for page in prs.slides)
    assert report.pictures == 0 and report.editable_objects == report.total_objects
    assert report.charts == 1 and report.tables == 2 and report.notes_slides == len(slides)
    assert report.text_boxes == sum(1 for r in rendered for e in r.elements if e.kind == "text")
    assert all(check.ok for check in report.checks) and len(report.checks) >= 5


def test_only_image_nodes_become_pictures(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), "#2563EB").save(buffer, format="PNG")
    src = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    slides = [
        samples.slide(1, "bullets", "The team works from one office", [ImageNode(src=src, alt="Office")]),
        samples.slide(2, "bullets", "A picture is planned here", [ImageNode(prompt="a busy office", alt="Office")]),
    ]
    path = tmp_path / "images.pptx"
    rendered, prs = export(slides, path)
    pictures = [s for page in prs.slides for s in page.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1                       # the node without a source stays an editable placeholder
    report = build_report(path, rendered)
    assert report.pictures == 1 and report.editable_objects == report.total_objects - 1
    assert all(check.ok for check in report.checks)
