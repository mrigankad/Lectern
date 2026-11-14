"""Brand kits (U09): upload a template, extract the brand, edit rules, apply to decks, brand-match score."""
from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import store
from ..brand import kits
from ..brand.rules import KINDS, check_rule, classify, new_rule
from ..engine.place import place_deck
from ..db import session
from ..models import BrandKitRow, DeckRow
from sqlmodel import select

router = APIRouter(tags=["brand"])
MAX_BYTES = 60 * 1024 * 1024


class KitPatch(BaseModel):
    name: str | None = None
    fonts: dict[str, str] | None = None
    palette: list[dict[str, str]] | None = None
    primary_logo: str | None = None   # logo id; "" removes the logo from slides


class RuleIn(BaseModel):
    text: str = Field(min_length=1)


class RulePatch(BaseModel):
    text: str | None = None
    enabled: bool | None = None


class DeckKitIn(BaseModel):
    brand_kit_id: str | None = None


async def _read(upload: UploadFile, kinds: tuple[str, ...], label: str) -> bytes:
    name = (upload.filename or "").lower()
    if not name.endswith(kinds):
        raise store.Conflict(f"Upload a {label} file ({', '.join(kinds)}).")
    data = await upload.read()
    if not data:
        raise store.Conflict("The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise store.Conflict("That file is larger than 60 MB.")
    return data


def _ingest(fn: Any, *args: Any) -> BrandKitRow:
    try:
        return fn(*args)
    except ValueError as error:
        raise store.Conflict(str(error)) from error


@router.get("/brand-kits")
async def list_kits() -> list[dict[str, Any]]:
    out = []
    for row in kits.list_kits():
        item = kits.summary(row)
        item["deck_count"] = 0
        out.append(item)
    counts: dict[str, int] = {}
    with session() as s:
        for theme in s.exec(select(DeckRow.theme)).all():
            kit = (theme or {}).get("brand_kit_id")
            if kit:
                counts[kit] = counts.get(kit, 0) + 1
    for item in out:
        item["deck_count"] = counts.get(item["id"], 0)
    return out


@router.post("/brand-kits", status_code=201)
async def create_kit(name: str = Form(""), template: UploadFile | None = File(None),
                     guide: UploadFile | None = File(None)) -> dict[str, Any]:
    template_data = await _read(template, (".potx", ".pptx"), "PowerPoint template") if template else None
    guide_data = await _read(guide, (".pdf",), "PDF") if guide else None
    row = kits.save(BrandKitRow(name=name.strip() or "Untitled brand kit"))
    try:
        if template_data is not None:
            row = _ingest(kits.ingest_template, row, template_data, template.filename or "")  # type: ignore[union-attr]
        if guide_data is not None:
            row = _ingest(kits.ingest_guide, row, guide_data)
        if template_data is None and guide_data is None:
            kits.rebuild_theme(row)
            row = kits.save(row)
    except store.Conflict:
        kits.delete_kit(row.id)
        raise
    return kits.summary(row)


@router.get("/brand-kits/{kit_id}")
async def get_kit(kit_id: str) -> dict[str, Any]:
    item = kits.summary(kits.get_kit(kit_id))
    with session() as s:
        rows = s.exec(select(DeckRow).order_by(DeckRow.updated_at.desc())).all()  # type: ignore[attr-defined]
    item["decks"] = [{"id": r.id, "title": r.title} for r in rows if (r.theme or {}).get("brand_kit_id") == kit_id]
    return item


@router.patch("/brand-kits/{kit_id}")
async def patch_kit(kit_id: str, body: KitPatch) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    if body.name is not None and body.name.strip():
        row.name = body.name.strip()
    if body.fonts is not None:
        row.fonts = {k: v.strip() for k, v in body.fonts.items() if v and v.strip()}
    if body.palette is not None:
        row.palette = body.palette
    if body.primary_logo is not None:
        row.logos = [{**l, "primary": l["id"] == body.primary_logo} for l in row.logos]
    kits.rebuild_theme(row)
    return kits.summary(kits.save(row))


@router.delete("/brand-kits/{kit_id}", status_code=204)
async def delete_kit(kit_id: str) -> None:
    kits.delete_kit(kit_id)


@router.post("/brand-kits/{kit_id}/template")
async def upload_template(kit_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    data = await _read(file, (".potx", ".pptx"), "PowerPoint template")
    return kits.summary(_ingest(kits.ingest_template, row, data, file.filename or ""))


@router.post("/brand-kits/{kit_id}/guide")
async def upload_guide(kit_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    data = await _read(file, (".pdf",), "PDF")
    return kits.summary(_ingest(kits.ingest_guide, row, data))


@router.get("/brand-kits/{kit_id}/files/{name}")
async def kit_file(kit_id: str, name: str) -> FileResponse:
    path = kits.kit_file(kit_id, name)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


# ---------------------------------------------------------------- rules
@router.post("/brand-kits/{kit_id}/rules", status_code=201)
async def add_rule(kit_id: str, body: RuleIn) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    rule = new_rule(body.text, "user", fonts=row.fonts, palette=[p["hex"] for p in row.palette])
    row.rules = [*row.rules, rule]
    return kits.summary(kits.save(row))


@router.patch("/brand-kits/{kit_id}/rules/{rule_id}")
async def patch_rule(kit_id: str, rule_id: str, body: RulePatch) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    rules = []
    found = False
    for rule in row.rules:
        if rule.get("id") == rule_id:
            found = True
            rule = dict(rule)
            if body.enabled is not None:
                rule["enabled"] = body.enabled
            if body.text is not None and body.text.strip():
                rule["text"] = body.text.strip()
                rule["kind"], rule["params"] = classify(rule["text"], row.fonts, [p["hex"] for p in row.palette])
        rules.append(rule)
    if not found:
        raise store.NotFound("That brand rule does not exist.")
    row.rules = rules
    return kits.summary(kits.save(row))


@router.delete("/brand-kits/{kit_id}/rules/{rule_id}")
async def delete_rule(kit_id: str, rule_id: str) -> dict[str, Any]:
    row = kits.get_kit(kit_id)
    row.rules = [r for r in row.rules if r.get("id") != rule_id]
    return kits.summary(kits.save(row))


# ---------------------------------------------------------------- decks
@router.put("/decks/{deck_id}/brand-kit")
async def set_deck_kit(deck_id: str, body: DeckKitIn) -> dict[str, Any]:
    deck = store.load_deck(deck_id)
    theme = kits.apply_to_deck(body.brand_kit_id or None, deck.id)
    if deck.status == "ready" or deck.slides:
        for slide in deck.slides:
            if slide.status == "ready":
                store.lint_and_sync(deck.id, slide.id, announce=False)
    return {"deck_id": deck.id, "brand_kit_id": theme.brand_kit_id, "theme": theme.model_dump()}


@router.get("/decks/{deck_id}/brand-match")
async def brand_match(deck_id: str) -> dict[str, Any]:
    """How well the deck follows its brand kit's enabled rules: per rule, the slides that break it."""
    deck = store.load_deck(deck_id)
    row = kits.kit_for_theme(deck.theme)
    if row is None:
        return {"brand_kit_id": None, "score": None, "rules": []}
    rendered = place_deck(deck.slides, deck.theme)
    results = []
    checks = passed = 0
    for rule in row.rules:
        checkable = rule.get("kind") in KINDS[:4]
        failing = []
        if checkable and rule.get("enabled", True):
            for slide, drawn in zip(deck.slides, rendered):
                problem = check_rule(rule, slide, drawn, deck.theme)
                checks += 1
                if problem:
                    failing.append({"slide_id": slide.id, "slide_index": slide.index, "detail": problem})
                else:
                    passed += 1
        results.append({"id": rule["id"], "text": rule["text"], "kind": rule.get("kind"),
                        "enabled": rule.get("enabled", True), "checkable": checkable,
                        "passed": not failing, "failing": failing})
    score = round(100 * passed / checks) if checks else 100
    return {"brand_kit_id": row.id, "brand_kit_name": row.name, "score": score, "rules": results}
