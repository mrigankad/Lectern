"""Share links (U14): a read-only web link to a deck, with access, download, notes and expiry settings,
and view counting (opens and time per slide). Owner endpoints live under /decks/{id}/shares; the public
viewer calls /public/shares/{token}. Passwords are stored as salted PBKDF2 hashes."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import delete, select

from .. import config, store
from ..db import session
from ..engine.place import place_deck
from ..export.pptx import build_pptx
from ..models import ShareLinkRow, ShareViewRow, new_id, now
from ..schema import RenderedSlide
from .export import PPTX_TYPE, _filename

router = APIRouter(tags=["shares"])
Access = Literal["anyone", "password"]
_ITERATIONS = 200_000


def Forbidden(detail: str) -> HTTPException:  # noqa: N802 - reads like an exception at the raise site
    return HTTPException(status_code=403, detail=detail)


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _algo, iterations, salt, digest = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(got, digest)


# ---------------------------------------------------------------- payloads
class SlideStat(BaseModel):
    index: int
    slide_id: str
    headline: str
    seconds: float
    avg_seconds: float


class ShareStats(BaseModel):
    opens: int
    visitors: int
    total_seconds: float
    avg_seconds: float
    slides: list[SlideStat]
    most_viewed: SlideStat | None = None


class ShareLink(BaseModel):
    id: str
    deck_id: str
    token: str
    path: str                 # "/s/{token}", relative to the web app
    access: Access
    has_password: bool
    allow_download: bool
    show_notes: bool
    expires_at: str | None
    expired: bool
    created_at: str
    stats: ShareStats


class ShareCreate(BaseModel):
    access: Access = "anyone"
    password: str | None = None
    allow_download: bool = False
    show_notes: bool = False
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ShareUpdate(BaseModel):
    access: Access | None = None
    password: str | None = None
    allow_download: bool | None = None
    show_notes: bool | None = None
    expires_in_days: int | None = Field(default=None, ge=0, le=365)   # 0 = never


class OpenIn(BaseModel):
    password: str | None = None
    visitor: str | None = Field(default=None, max_length=64)


class PublicSlide(BaseModel):
    id: str
    index: int
    headline: str
    notes: str | None = None


class OpenOut(BaseModel):
    view_id: str
    title: str
    allow_download: bool
    show_notes: bool
    slides: list[PublicSlide]
    render: list[RenderedSlide]


class PingIn(BaseModel):
    slide_id: str
    seconds: float = Field(ge=0, le=600)


class Probe(BaseModel):
    title: str
    requires_password: bool
    slide_count: int


# ---------------------------------------------------------------- helpers
def _expires(days: int | None) -> str | None:
    if not days:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_expired(row: ShareLinkRow) -> bool:
    if not row.expires_at:
        return False
    return datetime.fromisoformat(row.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)


def _stats(row: ShareLinkRow) -> ShareStats:
    with session() as s:
        views = s.exec(select(ShareViewRow).where(ShareViewRow.share_id == row.id)).all()
    slides = store.slide_rows(row.deck_id)
    opens = len(views)
    visitors = len({v.visitor or v.id for v in views})
    per: dict[str, float] = {}
    for v in views:
        for sid, sec in (v.slide_seconds or {}).items():
            per[sid] = per.get(sid, 0.0) + float(sec)
    total = sum(per.values())
    stat_slides = [SlideStat(index=s.position, slide_id=s.id, headline=s.headline, seconds=round(per.get(s.id, 0), 1),
                             avg_seconds=round(per.get(s.id, 0) / opens, 1) if opens else 0) for s in slides]
    most = max(stat_slides, key=lambda x: x.seconds) if total > 0 else None
    return ShareStats(opens=opens, visitors=visitors, total_seconds=round(total, 1),
                      avg_seconds=round(total / opens, 1) if opens else 0, slides=stat_slides, most_viewed=most)


def _to_link(row: ShareLinkRow) -> ShareLink:
    return ShareLink(id=row.id, deck_id=row.deck_id, token=row.token, path=f"/s/{row.token}",
                     access=row.access, has_password=bool(row.password_hash),  # type: ignore[arg-type]
                     allow_download=row.allow_download, show_notes=row.show_notes, expires_at=row.expires_at,
                     expired=_is_expired(row), created_at=row.created_at, stats=_stats(row))


def _owned(deck_id: str, share_id: str) -> ShareLinkRow:
    store.get_deck_row(deck_id)
    with session() as s:
        row = s.get(ShareLinkRow, share_id)
    if row is None or row.deck_id != deck_id or row.revoked:
        raise store.NotFound("That share link does not exist.")
    return row


def _live(token: str) -> ShareLinkRow:
    with session() as s:
        row = s.exec(select(ShareLinkRow).where(ShareLinkRow.token == token)).first()
    if row is None or row.revoked:
        raise store.NotFound("This link does not exist or was turned off by its owner.")
    if _is_expired(row):
        raise store.NotFound("This link has expired. Ask the owner for a new one.")
    store.get_deck_row(row.deck_id)
    return row


def _view(row: ShareLinkRow, view_id: str) -> ShareViewRow:
    with session() as s:
        view = s.get(ShareViewRow, view_id)
    if view is None or view.share_id != row.id:
        raise store.NotFound("Open the link again.")
    return view


# ---------------------------------------------------------------- owner
@router.get("/decks/{deck_id}/shares", response_model=list[ShareLink])
async def list_shares(deck_id: str) -> list[ShareLink]:
    store.get_deck_row(deck_id)
    with session() as s:
        rows = s.exec(select(ShareLinkRow).where(ShareLinkRow.deck_id == deck_id, ShareLinkRow.revoked == False)  # noqa: E712
                      .order_by(ShareLinkRow.created_at)).all()  # type: ignore[arg-type]
    return [_to_link(r) for r in rows]


@router.post("/decks/{deck_id}/shares", response_model=ShareLink)
async def create_share(deck_id: str, body: ShareCreate | None = None) -> ShareLink:
    body = body or ShareCreate()
    store.get_deck_row(deck_id)
    if body.access == "password" and not (body.password or "").strip():
        raise store.Conflict("Set a password for a password-protected link.")
    row = ShareLinkRow(deck_id=deck_id, token=secrets.token_urlsafe(9), access=body.access,
                       password_hash=hash_password(body.password) if body.password else None,
                       allow_download=body.allow_download, show_notes=body.show_notes,
                       expires_at=_expires(body.expires_in_days))
    with session() as s:
        s.add(row)
        s.commit()
    return _to_link(row)


@router.patch("/decks/{deck_id}/shares/{share_id}", response_model=ShareLink)
async def update_share(deck_id: str, share_id: str, body: ShareUpdate) -> ShareLink:
    row = _owned(deck_id, share_id)
    fields = body.model_dump(exclude_unset=True)
    with session() as s:
        fresh = s.get(ShareLinkRow, row.id)
        assert fresh is not None
        if fields.get("password"):
            fresh.password_hash = hash_password(fields["password"])
        if fields.get("access"):
            if fields["access"] == "password" and not fresh.password_hash:
                raise store.Conflict("Set a password for a password-protected link.")
            fresh.access = fields["access"]
        for key in ("allow_download", "show_notes"):
            if fields.get(key) is not None:
                setattr(fresh, key, fields[key])
        if "expires_in_days" in fields:
            fresh.expires_at = _expires(fields["expires_in_days"])
        s.add(fresh)
        s.commit()
    return _to_link(fresh)


@router.delete("/decks/{deck_id}/shares/{share_id}")
async def delete_share(deck_id: str, share_id: str) -> dict[str, bool]:
    row = _owned(deck_id, share_id)
    with session() as s:
        s.exec(delete(ShareViewRow).where(ShareViewRow.share_id == row.id))  # type: ignore[call-overload,arg-type]
        s.exec(delete(ShareLinkRow).where(ShareLinkRow.id == row.id))  # type: ignore[call-overload,arg-type]
        s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- public viewer
@router.get("/public/shares/{token}", response_model=Probe)
async def probe(token: str) -> Probe:
    row = _live(token)
    deck = store.get_deck_row(row.deck_id)
    return Probe(title=deck.title, requires_password=row.access == "password",
                 slide_count=len(store.slide_rows(row.deck_id)))


@router.post("/public/shares/{token}/open", response_model=OpenOut, response_model_exclude_none=True)
async def open_share(token: str, body: OpenIn | None = None) -> OpenOut:
    body = body or OpenIn()
    row = _live(token)
    if row.access == "password" and not check_password(body.password or "", row.password_hash):
        raise Forbidden("That password is not right." if body.password else "This link needs a password.")
    deck = store.load_deck(row.deck_id)
    ready = [s for s in deck.slides if s.status == "ready"] or deck.slides
    view = ShareViewRow(share_id=row.id, visitor=body.visitor)
    with session() as s:
        s.add(view)
        s.commit()
    slides = [PublicSlide(id=s.id, index=s.index, headline=s.headline, notes=s.notes if row.show_notes else None)
              for s in ready]
    return OpenOut(view_id=view.id, title=deck.title, allow_download=row.allow_download,
                   show_notes=row.show_notes, slides=slides, render=place_deck(ready, deck.theme))


@router.post("/public/shares/{token}/views/{view_id}/ping")
async def ping(token: str, view_id: str, body: PingIn) -> dict[str, bool]:
    row = _live(token)
    view = _view(row, view_id)
    with session() as s:
        fresh = s.get(ShareViewRow, view.id)
        assert fresh is not None
        seconds = dict(fresh.slide_seconds or {})
        seconds[body.slide_id] = round(float(seconds.get(body.slide_id, 0)) + body.seconds, 1)
        fresh.slide_seconds = seconds
        fresh.last_seen_at = now()
        s.add(fresh)
        s.commit()
    return {"ok": True}


@router.get("/public/shares/{token}/download")
async def download(token: str, view_id: str) -> FileResponse:
    row = _live(token)
    _view(row, view_id)
    if not row.allow_download:
        raise Forbidden("The owner has not allowed downloads for this link.")
    deck = store.load_deck(row.deck_id)
    if not deck.slides:
        raise store.Conflict("This deck has no slides yet.")
    rendered = place_deck(deck.slides, deck.theme)
    filename = _filename(deck.title)
    path = config.exports_dir() / new_id("fl") / filename
    build_pptx(deck.slides, rendered, deck.theme, path, include_notes=row.show_notes, title=deck.title)
    return FileResponse(path, media_type=PPTX_TYPE, filename=filename)
