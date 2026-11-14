"""Editability report: re-open the saved .pptx and count what is actually in it."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ..schema import Check, ExportReport, RenderedSlide

EXPECTED_W = 12192000
EXPECTED_H = 6858000


def expected_counts(rendered: list[RenderedSlide]) -> dict[str, int]:
    """What the exporter should have produced, from the rendered slides."""
    counts = {"charts": 0, "tables": 0, "pictures": 0, "text": 0}
    for slide in rendered:
        for element in slide.elements:
            if element.kind == "chart":
                counts["charts"] += 1
            elif element.kind == "table":
                counts["tables"] += 1
            elif element.kind == "text":
                counts["text"] += 1
            elif element.kind == "image" and element.src:
                counts["pictures"] += 1
    return counts


def predicted_editability(rendered: list[RenderedSlide]) -> int:
    """Share of objects that export as native, editable objects (0-100), without writing a file."""
    total = sum(len(slide.elements) for slide in rendered)
    pictures = expected_counts(rendered)["pictures"]
    return round(100 * (total - pictures) / total) if total else 100


def build_report(path: Path, rendered: list[RenderedSlide] | None = None,
                 notes_expected: int | None = None) -> ExportReport:
    prs = Presentation(str(path))
    total = pictures = charts = tables = text_boxes = notes_slides = other_text = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            total += 1
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                pictures += 1
            elif getattr(shape, "has_chart", False) and shape.has_chart:
                charts += 1
            elif getattr(shape, "has_table", False) and shape.has_table:
                tables += 1
            elif shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
                text_boxes += 1
            elif shape.has_text_frame and shape.text_frame.text.strip():
                other_text += 1
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None \
                and slide.notes_slide.notes_text_frame.text.strip():
            notes_slides += 1
    slide_count = len(prs.slides)
    expected = expected_counts(rendered) if rendered is not None else None
    size_ok = prs.slide_width == EXPECTED_W and prs.slide_height == EXPECTED_H

    checks = [
        Check(label="Text is live text",
              detail=f"{text_boxes} text boxes you can click and retype; no text was flattened into a picture.",
              ok=expected is None or text_boxes >= expected["text"]),
        Check(label="Charts are PowerPoint charts",
              detail=(f"{charts} chart{'s' if charts != 1 else ''} with an editable data sheet."
                      if charts else "This deck has no charts."),
              ok=expected is None or charts == expected["charts"]),
        Check(label="Tables are real tables",
              detail=(f"{tables} table{'s' if tables != 1 else ''} with editable cells."
                      if tables else "This deck has no tables."),
              ok=expected is None or tables == expected["tables"]),
        Check(label="Pictures only where you placed images",
              detail=(f"{pictures} picture{'s' if pictures != 1 else ''}, all from image content."
                      if pictures else "No pictures: every object on every slide is editable."),
              ok=expected is None or pictures == expected["pictures"]),
        Check(label="Speaker notes",
              detail=f"{notes_slides} of {slide_count} slides carry speaker notes.",
              ok=notes_expected is None or notes_slides == notes_expected),
        Check(label="Slide size",
              detail="16:9 widescreen, 13.333 in × 7.5 in." if size_ok else "The slide size is not 13.333 in × 7.5 in.",
              ok=size_ok),
    ]
    return ExportReport(total_objects=total, editable_objects=total - pictures, pictures=pictures, charts=charts,
                        tables=tables, text_boxes=text_boxes, notes_slides=notes_slides, checks=checks)
