"""Data sources: upload files or links, preview sheets, suggest charts, and link cells to slides."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import store
from ..schema import Slide
from ..sources import analyst, link, refs, service

router = APIRouter(tags=["sources"])


class LinkIn(BaseModel):
    url: str
    deck_id: str | None = None
    name: str | None = None


class AttachIn(BaseModel):
    source_ids: list[str]


class SuggestIn(BaseModel):
    sheet: str | None = None
    range: str


class InsertIn(BaseModel):
    data_ref: str
    as_: Literal["chart", "stat"] = Field("chart", alias="as")
    kind: Literal["bar", "line", "area", "pie", "table"] | None = None
    title: str | None = None
    headline: str | None = None

    model_config = {"populate_by_name": True}


@router.get("/sources")
async def list_sources(deck_id: str | None = None) -> list[dict[str, Any]]:
    return [service.to_out(r) for r in service.list_sources(deck_id)]


@router.post("/sources/upload")
async def upload(request: Request, filename: str, deck_id: str | None = None) -> dict[str, Any]:
    """The raw file is the request body; `filename` names it (its extension picks the parser)."""
    return service.to_out(service.upload(await request.body(), filename, deck_id))


@router.post("/sources/link")
async def add_link(body: LinkIn) -> dict[str, Any]:
    """A web page (its text is read) or a public Google Sheets link (read through its CSV export)."""
    return service.to_out(service.add_link(body.url, body.deck_id, body.name))


@router.get("/sources/{source_id}")
async def get_source(source_id: str) -> dict[str, Any]:
    return service.to_out(service.get(source_id))


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str) -> dict[str, bool]:
    service.delete(source_id)
    return {"ok": True}


@router.post("/sources/{source_id}/reload")
async def reload_source(source_id: str) -> dict[str, Any]:
    return service.to_out(service.reload(source_id))


@router.put("/sources/{source_id}/file")
async def replace_file(source_id: str, request: Request) -> dict[str, Any]:
    return service.to_out(service.replace_file(source_id, await request.body()))


@router.get("/sources/{source_id}/file")
async def download(source_id: str) -> FileResponse:
    row = service.get(source_id)
    return FileResponse(service.original_path(row.id), filename=row.name if row.kind != "url" else f"{row.name}.html")


@router.get("/sources/{source_id}/preview")
async def preview(source_id: str, sheet: str | None = None) -> dict[str, Any]:
    row = service.get(source_id)
    parsed = service.parsed(source_id)
    sheets = parsed.get("sheets") or []
    out: dict[str, Any] = {"source": service.to_out(row), "sheets": [s["name"] for s in sheets],
                           "chunks": parsed.get("chunks") or []}
    if sheets:
        grid = service.sheet(source_id, sheet)
        out["sheet"] = grid["name"]
        out["rows"] = grid["rows"]
    return out


@router.get("/sources/{source_id}/analysis")
async def analysis(source_id: str) -> dict[str, Any]:
    return analyst.analyze(source_id)


@router.post("/sources/{source_id}/suggest")
async def suggest(source_id: str, body: SuggestIn) -> dict[str, Any]:
    """A chart for a range: the kind with a reason, the alternatives, and the linked data_ref."""
    row = service.get(source_id)
    grid = service.sheet(source_id, body.sheet)
    try:
        rng = refs.parse_range(body.range)
    except ValueError as error:
        raise store.Conflict(str(error)) from error
    cells = refs.read(grid["rows"], rng)
    result = analyst.suggest(cells)
    result.pop("table", None)
    result["data_ref"] = str(refs.Ref(row.name, grid["name"], rng))
    result["cells_label"] = f"{grid['name']}, {rng.label}"
    result["range"] = rng.a1
    result["sheet"] = grid["name"]
    return result


@router.post("/decks/{deck_id}/sources")
async def attach(deck_id: str, body: AttachIn) -> list[dict[str, Any]]:
    store.get_deck_row(deck_id)
    service.attach(body.source_ids, deck_id)
    return [service.to_out(r) for r in service.list_sources(deck_id)]


@router.get("/decks/{deck_id}/slides/{slide_id}/data")
async def slide_data(deck_id: str, slide_id: str) -> dict[str, Any]:
    """What on the slide is linked, and the numbers that disagree with the sheet."""
    slide = store.to_slide(store.get_slide_row(deck_id, slide_id))
    linked = [{"node": i, "type": n.type, "data_ref": link.linked_ref(n)}
              for i, n in enumerate(slide.nodes) if link.linked_ref(n)]
    return {"slide_id": slide.id, "index": slide.index, "linked": linked,
            "mismatches": link.mismatches(slide, deck_id)}


@router.post("/decks/{deck_id}/slides/{slide_id}/data/insert", response_model=Slide,
             response_model_exclude_none=True)
async def insert(deck_id: str, slide_id: str, body: InsertIn) -> Slide:
    return link.insert(deck_id, slide_id, body.data_ref, body.as_, body.kind, body.title, body.headline)


@router.post("/decks/{deck_id}/slides/{slide_id}/data/refresh")
async def refresh(deck_id: str, slide_id: str, update_text: bool = True) -> dict[str, Any]:
    """Refresh linked charts and stats. Figures in the prose written from the old values are rewritten
    (`text_updates`, old -> new); ambiguous ones come back in `flagged`, and any drift left shows in
    `mismatches`. `?update_text=false` only offers the text updates."""
    slide, changed, updates, flagged = link.refresh(deck_id, slide_id, update_text=update_text)
    return {"slide": slide.model_dump(exclude_none=True), "changed": changed, "text_updates": updates,
            "text_updated": bool(updates) and update_text, "flagged": flagged,
            "mismatches": link.mismatches(slide, deck_id)}


@router.post("/decks/{deck_id}/slides/{slide_id}/data/fix-numbers")
async def fix_numbers(deck_id: str, slide_id: str) -> dict[str, Any]:
    slide, count = link.fix_numbers(deck_id, slide_id)
    return {"slide": slide.model_dump(exclude_none=True), "fixed": count}
