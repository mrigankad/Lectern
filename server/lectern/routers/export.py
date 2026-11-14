"""Export to .pptx and file download."""
from __future__ import annotations

import re
import shutil

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .. import config, store
from ..engine.place import place_deck
from ..export.pptx import build_pptx, video_notes
from ..export.report import build_report
from ..models import new_id
from ..schema import ExportIn, ExportOut
from ..brand import kits
from ..export.pdf import build_images, build_notes_markdown, build_pdf, file_report

router = APIRouter(tags=["export"])
PPTX_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
FILE_TYPES = {".pptx": PPTX_TYPE, ".pdf": "application/pdf", ".zip": "application/zip",
              ".md": "text/markdown; charset=utf-8"}


def _filename(title: str, ext: str = "pptx") -> str:
    stem = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip()
    stem = re.sub(r"\s+", " ", stem)[:80].strip()
    return f"{stem or 'Deck'}.{ext}"


@router.post("/decks/{deck_id}/export", response_model=ExportOut)
async def export_deck(deck_id: str, body: ExportIn | None = None) -> ExportOut:
    options = body or ExportIn()
    deck = store.load_deck(deck_id)
    if deck.status in {"draft", "building"}:
        raise store.Conflict("The deck is still being generated. Export it once it is ready.")
    if not deck.slides:
        raise store.Conflict("This deck has no slides to export.")
    rendered = kits.resolve_sources(place_deck(deck.slides, deck.theme))
    if options.format != "pptx":  # pdf, images, notes
        return export_other(deck, rendered, options.format, options.include_notes)
    file_id = new_id("fl")
    filename = _filename(deck.title)
    path = config.exports_dir() / file_id / filename
    build_pptx(deck.slides, rendered, deck.theme, path, include_notes=options.include_notes, title=deck.title,
               template=kits.template_path(deck.theme))
    notes_expected = sum(1 for s in deck.slides if s.notes.strip() or video_notes(s)) if options.include_notes else 0
    report = build_report(path, rendered, notes_expected=notes_expected)
    return ExportOut(file_id=file_id, filename=filename, bytes=path.stat().st_size, report=report)


@router.get("/files/{file_id}")
async def download(file_id: str) -> FileResponse:
    if not re.fullmatch(r"fl_[0-9a-f]{12}", file_id):
        raise store.NotFound("That file does not exist.")
    folder = config.exports_dir() / file_id
    files = sorted(p for p in folder.iterdir() if p.suffix in FILE_TYPES) if folder.is_dir() else []
    if not files:
        raise store.NotFound("That file does not exist. Export the deck again.")
    return FileResponse(files[0], media_type=FILE_TYPES[files[0].suffix], filename=files[0].name)


def export_other(deck, rendered, fmt: str, include_notes: bool) -> ExportOut:  # type: ignore[no-untyped-def]
    """PDF (vector, fonts embedded), PNG per slide (zip) or speaker notes (Markdown)."""
    file_id = new_id("fl")
    folder = config.exports_dir() / file_id
    font_dirs = tuple(p for p in [kits.brand_dir(deck.theme.brand_kit_id)] if deck.theme.brand_kit_id)
    if fmt == "notes":
        path = build_notes_markdown(deck.slides, deck.title, folder / _filename(f"{deck.title} speaker notes", "md"))
    elif fmt == "images":
        pdf = build_pdf(deck.slides, rendered, deck.theme, config.exports_dir() / f"{file_id}_tmp" / "slides.pdf",
                        title=deck.title, font_dirs=font_dirs)
        path, _count = build_images(pdf, folder / _filename(f"{deck.title} slides", "zip"), _filename(deck.title, "")[:-1])
        shutil.rmtree(pdf.parent, ignore_errors=True)
    else:
        path = build_pdf(deck.slides, rendered, deck.theme, folder / _filename(deck.title, "pdf"),
                         include_notes=include_notes, title=deck.title, font_dirs=font_dirs)
    report = file_report(fmt, rendered, deck.slides, deck.theme, include_notes)
    return ExportOut(file_id=file_id, filename=path.name, bytes=path.stat().st_size, report=report)
