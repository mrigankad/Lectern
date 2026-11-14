"""Brand kit storage: rows in `brand_kit`, files under data/brand/{kit_id}/."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image
from sqlmodel import select

from .. import config
from ..db import session
from ..models import BrandKitRow, DeckRow, now
from ..schema import RenderedSlide, Theme
from ..store import NotFound
from . import extract
from .rules import suggested_rules

LOGO_URL = re.compile(r"^(?:https?://[^/]+)?/api/brand-kits/(bk_[0-9a-f]{12})/files/([\w.\-]+)$")


def brand_dir(kit_id: str | None = None) -> Path:
    path = config.data_dir() / "brand"
    if kit_id:
        path = path / kit_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_kit(kit_id: str) -> BrandKitRow:
    with session() as s:
        row = s.get(BrandKitRow, kit_id)
    if row is None:
        raise NotFound("That brand kit does not exist.")
    return row


def list_kits() -> list[BrandKitRow]:
    with session() as s:
        return list(s.exec(select(BrandKitRow).order_by(BrandKitRow.updated_at.desc())).all())  # type: ignore[attr-defined]


def save(row: BrandKitRow) -> BrandKitRow:
    row.updated_at = now()
    with session() as s:
        s.add(row)
        s.commit()
        s.refresh(row)
    return row


def delete_kit(kit_id: str) -> None:
    row = get_kit(kit_id)
    with session() as s:
        s.delete(s.get(BrandKitRow, row.id))
        s.commit()
    shutil.rmtree(config.data_dir() / "brand" / kit_id, ignore_errors=True)


def file_url(kit_id: str, name: str) -> str:
    return f"/api/brand-kits/{kit_id}/files/{name}"


def kit_file(kit_id: str, name: str) -> Path:
    if not re.fullmatch(r"[\w.\-]+", name) or not re.fullmatch(r"bk_[0-9a-f]{12}", kit_id):
        raise NotFound("That file does not exist.")
    path = config.data_dir() / "brand" / kit_id / name
    if not path.is_file():
        raise NotFound("That file does not exist.")
    return path


def logo_theme(row: BrandKitRow) -> tuple[str | None, float | None]:
    primary = next((l for l in row.logos if l.get("primary")), row.logos[0] if row.logos else None)
    if not primary:
        return None, None
    return file_url(row.id, primary["file"]), round(primary["width"] / max(1, primary["height"]), 3)


def rebuild_theme(row: BrandKitRow) -> None:
    logo, ratio = logo_theme(row)
    theme = extract.theme_from(row.name, row.palette, row.fonts, row.id, logo)
    theme.logo_ratio = ratio
    row.theme = theme.model_dump()


# ---------------------------------------------------------------- uploads
def ingest_template(row: BrandKitRow, data: bytes, filename: str) -> BrandKitRow:
    found = extract.extract_template(data, filename)
    folder = brand_dir(row.id)
    suffix = ".potx" if filename.lower().endswith(".potx") else ".pptx"
    for old in folder.glob("template.*"):
        old.unlink()
    for old in folder.glob("logo-*"):
        old.unlink()
    (folder / f"template{suffix}").write_bytes(data)
    row.template_file = f"template{suffix}"
    if not row.name or row.name == "Untitled brand kit":
        row.name = found.name
    row.palette = found.palette
    row.fonts = found.fonts
    row.layouts = found.layouts
    logos = []
    for n, (blob, ext, w, h) in enumerate(found.logos, start=1):
        name = f"logo-{n}.{ext}"
        (folder / name).write_bytes(blob)
        try:
            with Image.open(folder / name) as image:
                w, h = image.size
        except Exception:
            pass
        logos.append({"id": f"logo-{n}", "file": name, "width": w, "height": h, "primary": n == 1})
    row.logos = logos
    keep = [r for r in row.rules if r.get("source") == "user"]
    guide = [r for r in row.rules if r.get("source") == "guide"]
    row.rules = [*suggested_rules(found.palette, found.fonts, bool(logos), []), *guide, *keep]
    rebuild_theme(row)
    return save(row)


def ingest_guide(row: BrandKitRow, data: bytes) -> BrandKitRow:
    colors, fonts, sentences = extract.extract_guide(data)
    (brand_dir(row.id) / "guide.pdf").write_bytes(data)
    row.guide_file = "guide.pdf"
    known = {p["hex"] for p in row.palette}
    extra = [{"slot": "", "name": "From brand guide", "hex": c} for c in colors if c not in known][:8]
    row.palette = [*row.palette, *extra]
    if fonts and not row.fonts:
        row.fonts = {"heading": fonts[0], "body": fonts[0]}
    from .rules import new_rule

    existing = {r["text"] for r in row.rules}
    hexes = [p["hex"] for p in row.palette]
    row.rules = [*row.rules, *(new_rule(t, "guide", fonts=row.fonts, palette=hexes)
                               for t in sentences if t not in existing)]
    for rule in row.rules:  # keep the auto colour rule in step with the palette
        if rule.get("source") == "auto" and rule.get("kind") == "colors":
            rule["params"] = {"palette": hexes}
            rule["text"] = "Use only the brand colours: " + ", ".join(hexes)
    rebuild_theme(row)
    return save(row)


# ---------------------------------------------------------------- decks
def apply_to_deck(kit_id: str | None, deck_id: str) -> Theme:
    """Give a deck the kit's theme (or Lectern's default theme when kit_id is None)."""
    theme = Theme.model_validate(get_kit(kit_id).theme) if kit_id else Theme()
    with session() as s:
        deck = s.get(DeckRow, deck_id)
        if deck is None:
            raise NotFound("That deck does not exist.")
        deck.theme = theme.model_dump()
        deck.updated_at = now()
        s.add(deck)
        s.commit()
    return theme


def kit_for_theme(theme: Theme) -> BrandKitRow | None:
    if not theme.brand_kit_id:
        return None
    try:
        return get_kit(theme.brand_kit_id)
    except NotFound:
        return None


def template_path(theme: Theme) -> Path | None:
    row = kit_for_theme(theme)
    if row is None or not row.template_file:
        return None
    path = config.data_dir() / "brand" / row.id / row.template_file
    return path if path.is_file() else None


def resolve_sources(rendered: list[RenderedSlide]) -> list[RenderedSlide]:
    """Point brand-kit image URLs at the local files so the exporters can embed them."""
    out = []
    for slide in rendered:
        elements = []
        for e in slide.elements:
            match = LOGO_URL.match(e.src or "") if e.kind == "image" else None
            if match:
                path = config.data_dir() / "brand" / match.group(1) / match.group(2)
                e = e.model_copy(update={"src": str(path)})
            elements.append(e)
        out.append(slide.model_copy(update={"elements": elements}))
    return out


def summary(row: BrandKitRow) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "palette": row.palette, "fonts": row.fonts,
            "logos": [{**l, "url": file_url(row.id, l["file"])} for l in row.logos],
            "layouts": row.layouts, "rules": row.rules, "theme": row.theme,
            "template_file": row.template_file, "guide_file": row.guide_file,
            "created_at": row.created_at, "updated_at": row.updated_at}
