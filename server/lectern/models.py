"""Database tables."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class DeckRow(SQLModel, table=True):
    __tablename__ = "deck"
    id: str = Field(default_factory=lambda: new_id("dk"), primary_key=True)
    title: str = ""
    status: str = "draft"
    brief: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    theme: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    paused: bool = False
    error: str | None = None
    icon: str | None = None        # sidebar icon id chosen by the user
    icon_color: str | None = None  # sidebar icon colour id
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class SlideRow(SQLModel, table=True):
    __tablename__ = "slide"
    id: str = Field(default_factory=lambda: new_id("sl"), primary_key=True)
    deck_id: str = Field(index=True)
    position: int = 1
    section: str | None = None
    headline: str = ""
    layout: str = "bullets"
    intent: str | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    notes: str = ""
    status: str = "queued"
    score: int | None = None


class SlideVersionRow(SQLModel, table=True):
    __tablename__ = "slide_version"
    id: str = Field(default_factory=lambda: new_id("sv"), primary_key=True)
    slide_id: str = Field(index=True)
    deck_id: str = Field(index=True)
    seq: int = 1
    reason: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: str = Field(default_factory=now)


class RunRow(SQLModel, table=True):
    __tablename__ = "run"
    id: str = Field(default_factory=lambda: new_id("rn"), primary_key=True)
    deck_id: str = Field(index=True)
    slide_id: str | None = None
    slide_index: int | None = None
    role: str = ""
    status: str = "running"  # running | done | failed
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    summary: str = ""
    error: str | None = None
    started_at: str = Field(default_factory=now)
    ended_at: str | None = None


class MessageRow(SQLModel, table=True):
    __tablename__ = "message"
    id: str = Field(default_factory=lambda: new_id("ms"), primary_key=True)
    deck_id: str = Field(index=True)
    role: str = "user"  # user | assistant
    scope: str = "slide"
    slide_id: str | None = None
    text: str = ""
    status: str = "done"  # pending | done | failed
    result: str | None = None
    version_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    changed_slide_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: str = Field(default_factory=now)
    undone_at: str | None = None  # set when the Ask's changes were undone (store.undo_message)


class FindingRow(SQLModel, table=True):
    __tablename__ = "finding"
    id: str = Field(default_factory=lambda: new_id("fd"), primary_key=True)
    deck_id: str = Field(index=True)
    slide_id: str = Field(index=True)
    rule: str = ""
    key: str = ""  # stable fingerprint of the issue within the slide
    severity: str = "low"
    title: str = ""
    detail: str = ""
    status: str = "open"  # open | fixed | kept
    rule_id: str | None = None  # the user rule created when this finding was kept
    created_at: str = Field(default_factory=now)


class RuleRow(SQLModel, table=True):
    __tablename__ = "rule"
    id: str = Field(default_factory=lambda: new_id("rl"), primary_key=True)
    text: str = ""
    source: str | None = None
    created_at: str = Field(default_factory=now)


class ConnectionRow(SQLModel, table=True):
    __tablename__ = "connection"
    id: str = Field(primary_key=True)
    label: str = ""
    kind: str = ""  # offline | anthropic | openai_compatible
    base_url: str | None = None
    api_key: str | None = None
    status: str = "not_configured"  # connected | configured | not_configured | error
    detail: str | None = None
    position: int = 0


class RoleRouteRow(SQLModel, table=True):
    __tablename__ = "role_route"
    role: str = Field(primary_key=True)  # an agent role, or "_preset" holding the preset id in `provider`
    provider: str = ""
    model: str = ""


class MediaAssetRow(SQLModel, table=True):
    __tablename__ = "media_asset"
    id: str = Field(default_factory=lambda: new_id("ma"), primary_key=True)
    deck_id: str = Field(index=True)
    slide_id: str | None = Field(default=None, index=True)
    job_id: str | None = Field(default=None, index=True)
    provider: str = ""
    kind: str = "image"  # image | video
    prompt: str = ""
    aspect: str | None = None
    path: str = ""                 # relative to the media directory
    poster_path: str | None = None  # video poster frame, relative to the media directory
    mime: str = "image/png"
    width: int = 0
    height: int = 0
    cost_estimate: float | None = None
    created_at: str = Field(default_factory=now)


class MediaJobRow(SQLModel, table=True):
    __tablename__ = "media_job"
    id: str = Field(default_factory=lambda: new_id("mj"), primary_key=True)
    deck_id: str = Field(index=True)
    slide_id: str | None = None
    kind: str = "image"
    prompt: str = ""
    aspect: str = "16:9"
    style: str = ""
    providers: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "pending"  # pending | running | done | failed
    asset_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    errors: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: str = Field(default_factory=now)


class SettingRow(SQLModel, table=True):
    __tablename__ = "setting"
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class InterviewRow(SQLModel, table=True):
    """The Strategist's short interview before the outline (U04)."""
    __tablename__ = "interview"
    deck_id: str = Field(primary_key=True)
    questions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "open"  # open | done
    created_at: str = Field(default_factory=now)


class ShareLinkRow(SQLModel, table=True):
    __tablename__ = "share_link"
    id: str = Field(default_factory=lambda: new_id("sh"), primary_key=True)
    deck_id: str = Field(index=True)
    token: str = Field(index=True, unique=True)
    access: str = "anyone"  # anyone | password
    password_hash: str | None = None
    allow_download: bool = False
    show_notes: bool = False
    expires_at: str | None = None
    revoked: bool = False
    created_at: str = Field(default_factory=now)


class ShareViewRow(SQLModel, table=True):
    __tablename__ = "share_view"
    id: str = Field(default_factory=lambda: new_id("vw"), primary_key=True)
    share_id: str = Field(index=True)
    visitor: str | None = None
    slide_seconds: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    opened_at: str = Field(default_factory=now)
    last_seen_at: str = Field(default_factory=now)


class SourceRow(SQLModel, table=True):
    """A data source: an uploaded file or a fetched link, parsed into sheets or text chunks."""
    __tablename__ = "source"
    id: str = Field(default_factory=lambda: new_id("src"), primary_key=True)
    deck_id: str | None = Field(default=None, index=True)
    name: str = ""                 # file name as shown, also the first part of a data_ref
    kind: str = "csv"              # xlsx | csv | pdf | docx | text | url | gsheet
    url: str | None = None
    bytes: int = 0
    summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "ready"          # ready | failed
    error: str | None = None
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class BrandKitRow(SQLModel, table=True):
    """A brand kit (U09): what was extracted from an uploaded template and the brand rules."""
    __tablename__ = "brand_kit"
    id: str = Field(default_factory=lambda: new_id("bk"), primary_key=True)
    name: str = ""
    theme: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))       # Theme built from the kit
    palette: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))  # [{name, hex}]
    fonts: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))       # {heading, body}
    logos: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))  # [{id, file, width, height}]
    layouts: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))  # [{index, name, placeholders}]
    rules: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))  # [{id, text, kind, ...}]
    template_file: str | None = None   # file name under data/brand/{id}/
    guide_file: str | None = None      # brand PDF, if uploaded
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
