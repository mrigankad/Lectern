"""Media router, mirroring the model router: connections (kind "media"), the default provider, jobs,
storage under data/media/, and placing an asset on a slide."""
from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw
from sqlmodel import select

from .. import config, store
from ..db import session
from ..events import bus
from ..llm.retry import with_retries
from ..models import ConnectionRow, MediaAssetRow, MediaJobRow, SettingRow
from ..schema import ImageNode, Slide, Theme, ThemeColors
from .base import ASPECTS, DEFAULT_STYLE, Kind, MediaError, MediaProvider, MediaResult, image_size
from .higgsfield import HiggsfieldProvider
from .keyed import FluxProvider, GoogleProvider, OpenAIImagesProvider, RunwayProvider, StockProvider
from .offline import OfflineMediaProvider

log = logging.getLogger(__name__)
OFFLINE_ID = "offline"
PICTURE_LAYOUT_FALLBACK = {"title": "big_idea", "section": "big_idea", "closing": "big_idea",
                           "case_study": "bullets"}
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
              "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}


@dataclass(frozen=True)
class MediaSeed:
    id: str
    label: str
    kinds: tuple[Kind, ...]
    base_url: str | None
    needs_key: bool
    cost_hint: str
    build: Callable[[str, str | None], MediaProvider]
    generates: bool = True   # stock searches instead of generating; it is never the default


MEDIA_SEEDS: tuple[MediaSeed, ...] = (
    MediaSeed("higgsfield", "Higgsfield", ("image", "video"), None, False,
              "Uses your Higgsfield credits (about 0.25 per image, 5 per video).",
              lambda _key, _base: HiggsfieldProvider()),
    MediaSeed("google", "Google Imagen and Veo", ("image", "video"), None, True,
              "About $0.04 per image; Veo about $0.15 per second of video.",
              lambda key, base: GoogleProvider(key, base)),
    MediaSeed("openai_images", "OpenAI Images", ("image",), None, True, "About $0.04 per image.",
              lambda key, base: OpenAIImagesProvider(key, base)),
    MediaSeed("flux", "FLUX (fal.ai)", ("image",), None, True, "About $0.003 per image.",
              lambda key, base: FluxProvider(key, base)),
    MediaSeed("runway", "Runway", ("video", "image"), None, True, "About $0.80 per 8-second video.",
              lambda key, base: RunwayProvider(key, base)),
    MediaSeed("stock", "Stock photos (Pexels)", ("image", "video"), None, True, "Free with attribution.",
              lambda key, base: StockProvider(key, base), generates=False),
)
MEDIA_SEED_BY_ID = {seed.id: seed for seed in MEDIA_SEEDS}
_overrides: dict[str, MediaProvider] = {}
_tasks: set[asyncio.Task[None]] = set()


def set_provider_override(provider_id: str, provider: MediaProvider | None) -> None:
    """Replace a provider instance (tests use this to stub a network provider)."""
    if provider is None:
        _overrides.pop(provider_id, None)
    else:
        _overrides[provider_id] = provider


def clear_overrides() -> None:
    _overrides.clear()


# ---------------------------------------------------------------- connections and settings
def seed_defaults() -> None:
    with session() as s:
        for position, seed in enumerate(MEDIA_SEEDS):
            if s.get(ConnectionRow, seed.id) is None:
                s.add(ConnectionRow(id=seed.id, label=seed.label, kind="media", base_url=seed.base_url,
                                    status="not_configured", position=100 + position))
        s.commit()


def get_setting(key: str, default: Any = None) -> Any:
    with session() as s:
        row = s.get(SettingRow, key)
    return default if row is None or row.value is None else row.value


def set_setting(key: str, value: Any) -> None:
    with session() as s:
        row = s.get(SettingRow, key) or SettingRow(key=key)
        row.value = value
        s.add(row)
        s.commit()


def media_settings() -> dict[str, Any]:
    return {"auto_images": bool(get_setting("auto_images", False)),
            "default_provider": get_setting("default_media_provider"),
            "effective_default": default_provider()}


def update_settings(auto_images: bool | None, default: str | None) -> dict[str, Any]:
    if auto_images is not None:
        set_setting("auto_images", bool(auto_images))
    if default is not None:
        if default and default not in MEDIA_SEED_BY_ID and default != OFFLINE_ID:
            raise store.Conflict(f"There is no media provider called \"{default}\".")
        set_setting("default_media_provider", default or None)
    return media_settings()


def _row(provider_id: str) -> ConnectionRow | None:
    with session() as s:
        return s.get(ConnectionRow, provider_id)


def _key(row: ConnectionRow) -> str | None:
    return row.api_key or config.env_key(row.id)


def is_connected(provider_id: str) -> bool:
    if provider_id == OFFLINE_ID or provider_id in _overrides:
        return True
    seed = MEDIA_SEED_BY_ID.get(provider_id)
    row = _row(provider_id)
    if seed is None or row is None or config.force_offline():
        return False
    if not seed.needs_key:
        return row.status == "connected"     # the Higgsfield CLI counts once a test has succeeded
    return bool(_key(row))


def default_provider() -> str | None:
    """The configured media provider used for automatic images, or None when only offline is available."""
    chosen = get_setting("default_media_provider")
    if chosen and chosen != OFFLINE_ID and is_connected(chosen):
        return chosen
    for seed in MEDIA_SEEDS:
        if seed.generates and "image" in seed.kinds and is_connected(seed.id):
            return seed.id
    return None


def build(provider_id: str, colors: ThemeColors | None = None) -> MediaProvider:
    if provider_id in _overrides:
        return _overrides[provider_id]
    if provider_id == OFFLINE_ID:
        return OfflineMediaProvider(colors)
    seed = MEDIA_SEED_BY_ID.get(provider_id)
    row = _row(provider_id)
    if seed is None or row is None:
        raise MediaError(f"There is no media provider called \"{provider_id}\".")
    return seed.build(_key(row) or "", row.base_url)


def list_providers() -> list[dict[str, Any]]:
    default = default_provider()
    items = [{"id": OFFLINE_ID, "label": "Offline placeholders", "kinds": ["image"], "connected": True,
              "is_default": default is None, "detail": "Flat illustrations drawn in the deck's colours, no network.",
              "cost_hint": "Free"}]
    for seed in MEDIA_SEEDS:
        row = _row(seed.id)
        items.append({"id": seed.id, "label": seed.label, "kinds": list(seed.kinds),
                      "connected": is_connected(seed.id), "is_default": seed.id == default,
                      "detail": row.detail if row else None, "cost_hint": seed.cost_hint})
    return items


async def test_connection(provider_id: str) -> tuple[bool, str, list[str] | None]:
    seed = MEDIA_SEED_BY_ID[provider_id]
    row = _row(provider_id)
    if seed.needs_key and not (row and _key(row)):
        ok, detail = False, "Add an API key first."
    else:
        try:
            ok, detail = await build(provider_id).test()
        except MediaError as error:
            ok, detail = False, str(error)
    with session() as s:
        fresh = s.get(ConnectionRow, provider_id)
        if fresh is not None:
            fresh.status = "connected" if ok else ("error" if (_key(fresh) or not seed.needs_key) else "not_configured")
            fresh.detail = detail
            s.add(fresh)
            s.commit()
    return ok, detail, None


# ---------------------------------------------------------------- storage
def _deck_folder(deck_id: str) -> Path:
    folder = config.media_dir() / deck_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def draw_poster(width: int, height: int, colors: ThemeColors | None = None) -> bytes:
    """A plain poster frame with a play mark, for videos whose provider gave no preview image."""
    colors = colors or ThemeColors()
    width, height = (width or 1280), (height or 720)
    image = Image.new("RGB", (width, height), colors.ink)
    d = ImageDraw.Draw(image)
    r = min(width, height) * 0.12
    cx, cy = width / 2, height / 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colors.accent)
    d.polygon([(cx - r * 0.35, cy - r * 0.5), (cx - r * 0.35, cy + r * 0.5), (cx + r * 0.55, cy)], fill="#FFFFFF")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _poster_png(data: bytes) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "PNG")
            return buffer.getvalue()
    except Exception:
        return None


def save_asset(deck_id: str, result: MediaResult, *, provider: str, prompt: str, aspect: str | None,
               slide_id: str | None = None, job_id: str | None = None,
               colors: ThemeColors | None = None) -> MediaAssetRow:
    row = MediaAssetRow(deck_id=deck_id, slide_id=slide_id, job_id=job_id, provider=provider, kind=result.kind,
                        prompt=prompt, aspect=aspect, mime=result.mime, width=result.width, height=result.height,
                        cost_estimate=result.cost_estimate)
    folder = _deck_folder(deck_id)
    name = row.id + EXTENSIONS.get(result.mime, ".mp4" if result.kind == "video" else ".png")
    (folder / name).write_bytes(result.data)
    row.path = f"{deck_id}/{name}"
    if result.kind == "image" and not (row.width and row.height):
        row.width, row.height = image_size(result.data)
    if result.kind == "video":
        poster = _poster_png(result.poster) if result.poster else None
        poster = poster or draw_poster(row.width, row.height, colors)
        (folder / f"{row.id}_poster.png").write_bytes(poster)
        row.poster_path = f"{deck_id}/{row.id}_poster.png"
        if not (row.width and row.height):
            row.width, row.height = image_size(poster)
    with session() as s:
        s.add(row)
        s.commit()
    return row


def get_asset(asset_id: str) -> MediaAssetRow:
    with session() as s:
        row = s.get(MediaAssetRow, asset_id)
    if row is None:
        raise store.NotFound("That media file does not exist.")
    return row


def file_of(row: MediaAssetRow, poster: bool = False) -> Path:
    relative = row.poster_path if poster else row.path
    if not relative:
        raise store.NotFound("That media file has no poster frame." if poster else "That media file is missing.")
    path = (config.media_dir() / relative).resolve()
    if config.media_dir().resolve() not in path.parents or not path.is_file():
        raise store.NotFound("That media file is missing from disk.")
    return path


def picture_path(asset_id: str) -> Path | None:
    """The still picture for an asset (a video's poster frame), for export. None when unknown."""
    try:
        row = get_asset(asset_id)
        return file_of(row, poster=row.kind == "video")
    except store.NotFound:
        return None


def list_assets(deck_id: str, slide_id: str | None = None, kind: str | None = None) -> list[MediaAssetRow]:
    with session() as s:
        query = select(MediaAssetRow).where(MediaAssetRow.deck_id == deck_id)
        if slide_id:
            query = query.where(MediaAssetRow.slide_id == slide_id)
        if kind:
            query = query.where(MediaAssetRow.kind == kind)
        return list(s.exec(query.order_by(MediaAssetRow.created_at.desc())).all())  # type: ignore[attr-defined]


def delete_deck_media(deck_id: str) -> None:
    import shutil

    with session() as s:
        for row in s.exec(select(MediaAssetRow).where(MediaAssetRow.deck_id == deck_id)).all():
            s.delete(row)
        for job in s.exec(select(MediaJobRow).where(MediaJobRow.deck_id == deck_id)).all():
            s.delete(job)
        s.commit()
    shutil.rmtree(config.media_dir() / deck_id, ignore_errors=True)


def asset_out(row: MediaAssetRow) -> dict[str, Any]:
    return {"id": row.id, "deck_id": row.deck_id, "slide_id": row.slide_id, "job_id": row.job_id,
            "provider": row.provider, "kind": row.kind, "prompt": row.prompt, "aspect": row.aspect,
            "url": f"/api/media/{row.id}/file",
            "poster_url": f"/api/media/{row.id}/poster" if row.poster_path else None,
            "mime": row.mime, "width": row.width, "height": row.height, "cost_estimate": row.cost_estimate,
            "created_at": row.created_at}


def job_out(row: MediaJobRow) -> dict[str, Any]:
    return {"id": row.id, "deck_id": row.deck_id, "slide_id": row.slide_id, "kind": row.kind, "prompt": row.prompt,
            "aspect": row.aspect, "providers": row.providers, "status": row.status, "asset_ids": row.asset_ids,
            "errors": row.errors, "created_at": row.created_at}


def list_jobs(deck_id: str) -> list[MediaJobRow]:
    with session() as s:
        return list(s.exec(select(MediaJobRow).where(MediaJobRow.deck_id == deck_id)
                           .order_by(MediaJobRow.created_at.desc())).all())  # type: ignore[attr-defined]


# ---------------------------------------------------------------- generation
def _publish(job: MediaJobRow) -> None:
    bus.publish(job.deck_id, "media.updated", {"job_id": job.id, "status": job.status, "asset_ids": job.asset_ids,
                                               "errors": job.errors, "slide_id": job.slide_id})


def _update_job(job_id: str, **fields: Any) -> MediaJobRow:
    with session() as s:
        job = s.get(MediaJobRow, job_id)
        assert job is not None
        for name, value in fields.items():
            setattr(job, name, value)
        s.add(job)
        s.commit()
    return job


async def generate_with(provider_id: str, prompt: str, kind: Kind, aspect: str, style: str,
                        colors: ThemeColors | None = None, attempts: int = 3,
                        sleep: Callable[[float], Any] = asyncio.sleep) -> list[MediaResult]:
    """One provider call with retries and exponential backoff on 429/5xx/connection errors."""
    provider = build(provider_id, colors)
    if kind not in provider.kinds:
        raise MediaError(f"{provider_id} cannot make {kind}s.")
    return await with_retries(lambda: provider.generate(prompt, kind, aspect, style), attempts=attempts,
                              base_delay=2.0, sleep=sleep)


def validate_request(kind: str, aspect: str, providers: list[str]) -> list[str]:
    if kind not in ("image", "video"):
        raise store.Conflict("Choose image or video.")
    if aspect not in ASPECTS:
        raise store.Conflict(f"Choose an aspect ratio: {', '.join(ASPECTS)}.")
    chosen = list(dict.fromkeys(providers or [default_provider() or OFFLINE_ID]))
    for provider_id in chosen:
        if provider_id != OFFLINE_ID and provider_id not in MEDIA_SEED_BY_ID:
            raise store.Conflict(f"There is no media provider called \"{provider_id}\".")
        if not is_connected(provider_id):
            raise store.Conflict(f"{provider_id} is not connected. Add its key under Connections and test it.")
    if kind == "video" and chosen == [OFFLINE_ID]:
        raise store.Conflict("The offline provider makes images only. Connect a video provider to make videos.")
    return chosen


def start_job(deck_id: str, prompt: str, kind: Kind, aspect: str, providers: list[str], style: str | None,
              slide_id: str | None) -> MediaJobRow:
    if not prompt.strip():
        raise store.Conflict("Write a prompt first.")
    deck = store.load_deck(deck_id)
    if slide_id and not any(s.id == slide_id for s in deck.slides):
        raise store.NotFound("That slide does not exist in this deck.")
    chosen = validate_request(kind, aspect, providers)
    job = MediaJobRow(deck_id=deck_id, slide_id=slide_id, kind=kind, prompt=prompt.strip(), aspect=aspect,
                      style=style if style is not None else DEFAULT_STYLE, providers=chosen)
    with session() as s:
        s.add(job)
        s.commit()
    task = asyncio.get_running_loop().create_task(run_job(job.id, deck.theme))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


async def run_job(job_id: str, theme: Theme | None = None) -> MediaJobRow:
    with session() as s:
        job = s.get(MediaJobRow, job_id)
    assert job is not None
    job = _update_job(job_id, status="running")
    _publish(job)
    colors = (theme or Theme()).colors
    asset_ids: list[str] = []
    errors: list[dict[str, str]] = []

    async def one(provider_id: str) -> None:
        try:
            results = await generate_with(provider_id, job.prompt, job.kind, job.aspect, job.style,  # type: ignore[arg-type]
                                          colors)
        except Exception as error:  # a failing provider must not sink the others
            errors.append({"provider": provider_id, "detail": str(error) or error.__class__.__name__})
            return
        if not results:
            errors.append({"provider": provider_id, "detail": "No results for this prompt."})
        for result in results:
            row = save_asset(job.deck_id, result, provider=provider_id, prompt=job.prompt, aspect=job.aspect,
                             slide_id=job.slide_id, job_id=job.id, colors=colors)
            asset_ids.append(row.id)

    await asyncio.gather(*(one(p) for p in job.providers))
    job = _update_job(job_id, status="done" if asset_ids else "failed", asset_ids=asset_ids, errors=errors)
    _publish(job)
    return job


async def wait_all() -> None:
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def upload(deck_id: str, data: bytes, content_type: str, filename: str | None,
           slide_id: str | None) -> MediaAssetRow:
    store.load_deck(deck_id)
    if not data:
        raise store.Conflict("The upload was empty.")
    if len(data) > 200 * 1024 * 1024:
        raise store.Conflict("That file is larger than 200 MB.")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in EXTENSIONS and filename:
        suffix = Path(filename).suffix.lower()
        mime = next((m for m, ext in EXTENSIONS.items() if ext == suffix or (suffix == ".jpeg" and ext == ".jpg")), mime)
    if mime not in EXTENSIONS:
        raise store.Conflict("Upload a PNG, JPEG, WebP or GIF image, or an MP4, WebM or MOV video.")
    kind: Kind = "video" if mime.startswith("video/") else "image"
    width, height = image_size(data) if kind == "image" else (0, 0)
    if kind == "image" and not width:
        raise store.Conflict("That image could not be read.")
    return save_asset(deck_id, MediaResult(data=data, mime=mime, kind=kind, width=width, height=height,
                                           cost_estimate=0.0),
                      provider="upload", prompt=filename or "Uploaded file", aspect=None, slide_id=slide_id)


# ---------------------------------------------------------------- prompts and placement
def suggest(slide: Slide | None, theme: Theme) -> dict[str, Any]:
    if slide is None:
        return {"prompt": "", "style": DEFAULT_STYLE, "slide_index": None, "headline": None}
    context = ""
    for node in slide.nodes:
        if node.type == "text" and node.role in ("subhead", "body"):
            context = node.value
            break
        if node.type == "bullets" and node.items:
            context = "; ".join(node.items[:3])
            break
        if node.type == "items" and node.items:
            context = "; ".join(item.title for item in node.items[:3])
            break
    prompt = f"An illustration for a presentation slide that says: \"{slide.headline}\""
    if context:
        prompt += f". Supporting points: {context}"
    prompt += (f". Use a {theme.colors.accent} accent on a light {theme.colors.bg} background with "
               f"{theme.colors.ink} details. No text, no logos.")
    return {"prompt": prompt, "style": DEFAULT_STYLE, "slide_index": slide.index, "headline": slide.headline}


def image_node(row: MediaAssetRow) -> ImageNode:
    src = f"/api/media/{row.id}/poster" if row.kind == "video" else f"/api/media/{row.id}/file"
    alt = row.prompt.strip()[:140] or ("Video" if row.kind == "video" else "Image")
    return ImageNode(src=src, asset_id=row.id, prompt=row.prompt or None, alt=alt)


def with_image(slide: Slide, row: MediaAssetRow) -> Slide:
    """The slide with the asset as its image node (replacing an existing one) in a layout that draws pictures."""
    node = image_node(row)
    nodes = list(slide.nodes)
    index = next((n for n, existing in enumerate(nodes) if existing.type == "image"), None)
    if index is None:
        nodes.append(node)
    else:
        nodes[index] = node
    layout = PICTURE_LAYOUT_FALLBACK.get(slide.layout, slide.layout)
    return slide.model_copy(update={"nodes": nodes, "layout": layout})


def place_on_slide(deck_id: str, slide_id: str, asset_id: str, reason: str = "Placed media") -> Slide:
    from ..agents import apply

    row = get_asset(asset_id)
    if row.deck_id != deck_id:
        raise store.NotFound("That media file belongs to another deck.")
    slide_row = store.get_slide_row(deck_id, slide_id)
    if not store.editable(slide_row):
        raise store.Conflict("This slide is being worked on by an agent. Try again in a moment.")
    slide = store.to_slide(slide_row)
    changed = with_image(slide, row)
    changed = apply.patched(slide, layout=changed.layout, nodes=changed.nodes)
    apply.save(deck_id, changed, reason)
    if row.slide_id != slide_id:
        with session() as s:
            fresh = s.get(MediaAssetRow, asset_id)
            if fresh is not None and fresh.slide_id is None:
                fresh.slide_id = slide_id
                s.add(fresh)
                s.commit()
    store.publish_deck(deck_id)
    return store.to_slide(store.get_slide_row(deck_id, slide_id))


# ---------------------------------------------------------------- the Art Director's automatic images
WANTS_PICTURE = frozenset({"big_idea", "bullets", "quote", "summary", "two_column"})
DATA_NODES = frozenset({"chart", "table", "stat", "image"})


def needs_image(slide: Slide) -> bool:
    return slide.layout in WANTS_PICTURE and not any(node.type in DATA_NODES for node in slide.nodes)


def auto_provider() -> str | None:
    """Provider for automatic images: the default media provider, else offline when `auto_images` is on."""
    chosen = default_provider()
    if chosen:
        return chosen
    return OFFLINE_ID if get_setting("auto_images", False) else None


async def auto_image(deck_id: str, slide: Slide, theme: Theme) -> MediaAssetRow | None:
    """Generate and attach one image for the slide. Returns the asset, or None when nothing was made."""
    provider_id = auto_provider()
    if provider_id is None or not needs_image(slide):
        return None
    prompt = suggest(slide, theme)["prompt"]
    results = await generate_with(provider_id, prompt, "image", "16:9", DEFAULT_STYLE, theme.colors)
    if not results:
        return None
    row = save_asset(deck_id, results[0], provider=provider_id, prompt=prompt, aspect="16:9", slide_id=slide.id,
                     colors=theme.colors)
    bus.publish(deck_id, "media.updated", {"job_id": None, "status": "done", "asset_ids": [row.id], "errors": [],
                                           "slide_id": slide.id})
    return row


