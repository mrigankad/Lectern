"""Export on a customer's template: the deck keeps the template's master, layouts, theme and logo."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx.enum.shapes import MSO_SHAPE_TYPE

from .extract import open_presentation

R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def open_template(path: Path) -> tuple[Any, Any, bool]:
    """(presentation with no slides, the layout to build slides on, whether the master already has a picture)."""
    prs = open_presentation(path.read_bytes())
    slide_ids = prs.slides._sldIdLst
    for entry in list(slide_ids):
        prs.part.drop_rel(entry.get(R_ID))
        slide_ids.remove(entry)
    master = prs.slide_masters[0]
    layouts = list(master.slide_layouts)
    blank = next((l for l in layouts if "blank" in (l.name or "").lower()), None)
    if blank is None:
        blank = min(layouts, key=lambda l: len(l.placeholders)) if layouts else prs.slide_layouts[0]
    has_logo = any(shape.shape_type == MSO_SHAPE_TYPE.PICTURE
                   for source in (master, blank) for shape in source.shapes)
    return prs, blank, has_logo


def strip_placeholders(page: Any) -> None:
    """Our content is drawn as free shapes; empty layout placeholders would show 'Click to add title'."""
    for shape in list(page.placeholders):
        shape._element.getparent().remove(shape._element)
