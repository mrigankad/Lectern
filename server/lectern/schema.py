"""Pydantic models: the scene graph (SPEC section 3) and API payloads (section 5)."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

LayoutId = Literal[
    "title", "agenda", "section", "big_idea", "bullets", "two_column", "three_column", "process",
    "timeline", "chart", "dashboard", "table", "quote", "case_study", "diagram", "team",
    "summary", "next_steps", "closing", "appendix", "big_number",
]
DeckStatus = Literal["interview", "draft", "outline_ready", "building", "ready", "failed"]
SlideStatus = Literal["queued", "writing", "rendering", "checking", "sent_back", "ready"]
TextRole = Literal["eyebrow", "headline", "subhead", "body", "caption"]
ChartKind = Literal["bar", "line", "area", "pie"]
Severity = Literal["high", "medium", "low"]
FindingStatus = Literal["open", "fixed", "kept"]
ROLES: tuple[str, ...] = ("strategist", "writer", "art_director", "renderer", "critic", "editor")


# ---------------------------------------------------------------- nodes
class TextNode(BaseModel):
    type: Literal["text"] = "text"
    role: TextRole = "body"
    value: str


class BulletsNode(BaseModel):
    type: Literal["bullets"] = "bullets"
    items: list[str]


class StatNode(BaseModel):
    type: Literal["stat"] = "stat"
    value: str
    caption: str | None = None
    source: str | None = None


class Series(BaseModel):
    name: str
    values: list[float]


class ChartNode(BaseModel):
    type: Literal["chart"] = "chart"
    kind: ChartKind = "bar"
    title: str | None = None
    categories: list[str]
    series: list[Series]
    unit: str | None = None
    data_ref: str | None = None


class TableNode(BaseModel):
    type: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[str]]


class QuoteNode(BaseModel):
    type: Literal["quote"] = "quote"
    text: str
    attribution: str | None = None


class Item(BaseModel):
    title: str
    body: str | None = None
    label: str | None = None


class ItemsNode(BaseModel):
    type: Literal["items"] = "items"
    style: Literal["columns", "steps", "timeline"] = "columns"
    items: list[Item]


class ImageNode(BaseModel):
    type: Literal["image"] = "image"
    src: str | None = None
    prompt: str | None = None
    alt: str = ""
    asset_id: str | None = None   # a stored media asset (media_asset table); src then points at its file


Node = Annotated[
    Union[TextNode, BulletsNode, StatNode, ChartNode, TableNode, QuoteNode, ItemsNode, ImageNode],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------- deck
class ThemeColors(BaseModel):
    bg: str = "#FFFFFF"
    ink: str = "#16181D"
    body: str = "#5E6370"
    muted: str = "#7A7F8C"
    line: str = "#E8E8EC"
    surface: str = "#F7F7F8"
    accent: str = "#2563EB"
    on_accent: str = "#FFFFFF"


class Theme(BaseModel):
    name: str = "Lectern"
    font: str = "Urbanist"
    colors: ThemeColors = Field(default_factory=ThemeColors)
    chart_colors: list[str] = Field(
        default_factory=lambda: ["#2563EB", "#16181D", "#7A7F8C", "#0E8F8E", "#7C5CFF", "#D9D9E0"]
    )
    brand_kit_id: str | None = None     # additive: the brand kit this theme came from (U09)
    logo: str | None = None             # additive: logo image URL drawn top right when a brand kit has one
    logo_ratio: float | None = None     # additive: logo width / height


class Brief(BaseModel):
    prompt: str
    audience: str | None = None
    goal: str | None = None
    minutes: int | None = None
    tone: str | None = None
    deck_type: str | None = None
    slide_count: int | None = None
    source_ids: list[str] | None = None            # additive: data sources attached to the deck
    data_facts: list[dict[str, Any]] | None = None  # additive: the Analyst's facts with cell/page refs


class Slide(BaseModel):
    id: str
    index: int
    section: str | None = None
    headline: str
    layout: LayoutId
    nodes: list[Node] = Field(default_factory=list)
    notes: str = ""
    status: SlideStatus = "queued"
    # True while this slide's next build step waits for a paused build to resume (status is the last step).
    paused: bool = False
    score: int | None = None
    intent: str | None = None  # additive: the Strategist's one-line intent


class Progress(BaseModel):
    ready: int
    total: int


class Deck(BaseModel):
    id: str
    title: str
    status: DeckStatus
    brief: Brief
    theme: Theme
    slides: list[Slide]
    created_at: str
    updated_at: str
    paused: bool = False            # additive
    progress: Progress              # additive
    error: str | None = None        # additive: why a deck is `failed`
    icon: str | None = None         # additive: sidebar icon id
    icon_color: str | None = None   # additive: sidebar icon colour id


class DeckSummary(BaseModel):
    id: str
    title: str
    status: DeckStatus
    slide_count: int
    updated_at: str
    progress: Progress
    icon: str | None = None
    icon_color: str | None = None


class DeckPatch(BaseModel):
    title: str | None = None
    icon: str | None = None
    icon_color: str | None = None


# ---------------------------------------------------------------- rendered form
class Style(BaseModel):
    font_size: float | None = None
    font_weight: Literal[400, 700] | None = None
    color: str | None = None
    align: Literal["left", "center", "right"] | None = None
    valign: Literal["top", "middle", "bottom"] | None = None
    line_height: float | None = None
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float | None = None
    uppercase: bool | None = None
    letter_spacing: float | None = None
    radius: float | None = None     # additive: corner radius in canvas px


class ChartSpec(BaseModel):
    kind: ChartKind
    categories: list[str]
    series: list[Series]
    colors: list[str]
    unit: str | None = None


class TableSpec(BaseModel):
    columns: list[str]
    rows: list[list[str]]


class Element(BaseModel):
    id: str
    node: int | None = None
    kind: Literal["text", "rect", "line", "chart", "table", "image"]
    x: float
    y: float
    w: float
    h: float
    text: str | None = None
    bullets: list[str] | None = None
    style: Style | None = None
    chart: ChartSpec | None = None
    table: TableSpec | None = None
    src: str | None = None
    alt: str | None = None


class RenderedSlide(BaseModel):
    id: str
    index: int
    width: Literal[1920] = 1920
    height: Literal[1080] = 1080
    background: str
    elements: list[Element]


# ---------------------------------------------------------------- API payloads
class DeckCreate(BaseModel):
    prompt: str = Field(min_length=1)
    audience: str | None = None
    goal: str | None = None
    minutes: int | None = None
    tone: str | None = None
    slide_count: int | None = None
    source_ids: list[str] | None = None  # additive: sources uploaded before the deck exists
    interview: bool = False  # additive: ask the Strategist's questions (U04) before drafting the outline


class OutlineSlideIn(BaseModel):
    id: str | None = None
    section: str | None = None
    headline: str
    layout: LayoutId = "bullets"
    intent: str | None = None


class OutlineUpdate(BaseModel):
    title: str
    slides: list[OutlineSlideIn]


class RegenerateIn(BaseModel):
    instruction: str | None = None


class SlidePatch(BaseModel):
    headline: str | None = None
    layout: LayoutId | None = None
    nodes: list[Node] | None = None
    notes: str | None = None
    section: str | None = None


class AskIn(BaseModel):
    scope: Literal["slide", "deck"] = "slide"
    slide_id: str | None = None
    message: str = Field(min_length=1)


class AskOut(BaseModel):
    message_id: str


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    scope: Literal["slide", "deck"]
    slide_id: str | None = None
    text: str
    status: Literal["pending", "done", "failed"]
    result: str | None = None
    version_ids: list[str] = Field(default_factory=list)
    changed_slide_ids: list[str] = Field(default_factory=list)
    created_at: str
    undone: bool = False


class Finding(BaseModel):
    id: str
    slide_id: str
    slide_index: int
    rule: str
    severity: Severity
    title: str
    detail: str
    status: FindingStatus


class CriticReport(BaseModel):
    score: int
    story: int
    design: int
    editability: int
    findings: list[Finding]


class FindingAction(BaseModel):
    action: Literal["fix", "keep", "reopen"]


class Rule(BaseModel):
    id: str
    text: str
    created_at: str
    source: str | None = None


class RuleCreate(BaseModel):
    text: str = Field(min_length=1)
    source: str | None = None


class ExportIn(BaseModel):
    format: Literal["pptx", "pdf", "images", "notes"] = "pptx"  # pdf, images (PNG zip), notes (Markdown)
    include_notes: bool = True


class Check(BaseModel):
    label: str
    detail: str
    ok: bool


class ExportReport(BaseModel):
    total_objects: int
    editable_objects: int
    pictures: int
    charts: int
    tables: int
    text_boxes: int
    notes_slides: int
    checks: list[Check]


class ExportOut(BaseModel):
    file_id: str
    filename: str
    bytes: int
    report: ExportReport


class Slot(BaseModel):
    name: str
    type: str                       # node type that fills the slot
    required: bool = False
    role: str | None = None         # text role, for text slots
    style: str | None = None        # items style, for items slots
    accepts: list[str] = Field(default_factory=list)  # other node types the slot also takes
    min_items: int | None = None
    max_items: int | None = None
    description: str = ""


class LayoutInfo(BaseModel):
    id: LayoutId
    name: str
    purpose: str
    best_for: str = ""
    slots: list[Slot]


class Connection(BaseModel):
    id: str
    label: str
    kind: str
    base_url: str | None = None
    has_key: bool
    status: str
    detail: str | None = None       # additive


class ConnectionUpdate(BaseModel):
    id: str
    api_key: str | None = None
    key: str | None = None          # alias of api_key
    base_url: str | None = None


class ConnectionTest(BaseModel):
    ok: bool
    detail: str
    models: list[str] | None = None


class RoleRoute(BaseModel):
    provider: str
    model: str


class Routing(BaseModel):
    preset: str
    roles: dict[str, RoleRoute]
    presets: list[dict[str, Any]] = Field(default_factory=list)  # additive: the available presets


class RoutingUpdate(BaseModel):
    preset: str | None = None
    roles: dict[str, RoleRoute] | None = None


class Run(BaseModel):
    id: str
    role: str
    slide_index: int | None = None
    status: str
    summary: str
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: str
    ended_at: str | None = None
