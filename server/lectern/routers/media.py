"""Media: generate images and videos, upload, list, download, and place an asset on a slide."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import store
from ..media import router as media
from ..schema import Slide

router = APIRouter(tags=["media"])


class GenerateIn(BaseModel):
    slide_id: str | None = None
    prompt: str
    kind: Literal["image", "video"] = "image"
    aspect: str = "16:9"
    providers: list[str] = Field(default_factory=list)
    style: str | None = None


class PlaceIn(BaseModel):
    asset_id: str


class MediaSettingsIn(BaseModel):
    auto_images: bool | None = None
    default_provider: str | None = None


@router.get("/media/providers")
async def providers() -> list[dict[str, Any]]:
    return media.list_providers()


@router.get("/settings/media")
async def get_media_settings() -> dict[str, Any]:
    return media.media_settings()


@router.put("/settings/media")
async def put_media_settings(body: MediaSettingsIn) -> dict[str, Any]:
    return media.update_settings(body.auto_images, body.default_provider)


@router.get("/decks/{deck_id}/media/suggest")
async def suggest(deck_id: str, slide_id: str | None = None) -> dict[str, Any]:
    deck = store.load_deck(deck_id)
    slide = next((s for s in deck.slides if s.id == slide_id), None) if slide_id else None
    if slide_id and slide is None:
        raise store.NotFound("That slide does not exist in this deck.")
    return media.suggest(slide, deck.theme)


@router.post("/decks/{deck_id}/media/generate", status_code=202)
async def generate(deck_id: str, body: GenerateIn) -> dict[str, Any]:
    """Starts a job; assets arrive with `media.updated` events (and in GET .../media/jobs)."""
    job = media.start_job(deck_id, body.prompt, body.kind, body.aspect, body.providers, body.style, body.slide_id)
    return media.job_out(job)


@router.get("/decks/{deck_id}/media/jobs")
async def jobs(deck_id: str) -> list[dict[str, Any]]:
    store.load_deck(deck_id)
    return [media.job_out(job) for job in media.list_jobs(deck_id)]


@router.get("/decks/{deck_id}/media")
async def list_media(deck_id: str, slide_id: str | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    store.load_deck(deck_id)
    return [media.asset_out(row) for row in media.list_assets(deck_id, slide_id, kind)]


@router.post("/decks/{deck_id}/media/upload")
async def upload(deck_id: str, request: Request, slide_id: str | None = None,
                 filename: str | None = None) -> dict[str, Any]:
    """The raw file is the request body; its Content-Type names the format."""
    data = await request.body()
    row = media.upload(deck_id, data, request.headers.get("content-type", ""), filename, slide_id)
    return media.asset_out(row)


@router.get("/media/{asset_id}/file")
async def file(asset_id: str) -> FileResponse:
    row = media.get_asset(asset_id)
    return FileResponse(media.file_of(row), media_type=row.mime)


@router.get("/media/{asset_id}/poster")
async def poster(asset_id: str) -> FileResponse:
    row = media.get_asset(asset_id)
    if row.kind == "image":
        return FileResponse(media.file_of(row), media_type=row.mime)
    return FileResponse(media.file_of(row, poster=True), media_type="image/png")


@router.post("/decks/{deck_id}/slides/{slide_id}/media", response_model=Slide, response_model_exclude_none=True)
async def place(deck_id: str, slide_id: str, body: PlaceIn) -> Slide:
    return media.place_on_slide(deck_id, slide_id, body.asset_id)
