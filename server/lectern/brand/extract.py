"""Read a .potx/.pptx template (and optionally a brand PDF) into a brand kit: colours, fonts, logos, layouts."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ..schema import Theme, ThemeColors

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
TEMPLATE_CT = b"application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"
PRESENTATION_CT = b"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
SCHEME_SLOTS = ("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6")
SLOT_NAMES = {"dk1": "Dark 1", "lt1": "Light 1", "dk2": "Dark 2", "lt2": "Light 2", "accent1": "Accent 1",
              "accent2": "Accent 2", "accent3": "Accent 3", "accent4": "Accent 4", "accent5": "Accent 5",
              "accent6": "Accent 6"}
HEX = re.compile(r"#([0-9A-Fa-f]{6})\b")


@dataclass
class Extraction:
    name: str = ""
    palette: list[dict[str, str]] = field(default_factory=list)          # [{slot, name, hex}]
    fonts: dict[str, str] = field(default_factory=dict)                   # {heading, body}
    logos: list[tuple[bytes, str, int, int]] = field(default_factory=list)  # (blob, ext, w px, h px)
    layouts: list[dict[str, Any]] = field(default_factory=list)
    slide_size: tuple[int, int] = (12192000, 6858000)
    guide_rules: list[str] = field(default_factory=list)                 # sentences from a brand PDF
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- opening templates
def as_presentation_bytes(data: bytes) -> bytes:
    """A .potx is a .pptx with another main content type; python-pptx only opens the latter."""
    if not _is_template(data):
        return data
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            blob = src.read(item.filename)
            if item.filename == "[Content_Types].xml":
                blob = blob.replace(TEMPLATE_CT, PRESENTATION_CT)
            dst.writestr(item, blob)
    return out.getvalue()


def _is_template(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return TEMPLATE_CT in z.read("[Content_Types].xml")
    except (zipfile.BadZipFile, KeyError):
        return False


def open_presentation(data: bytes):  # type: ignore[no-untyped-def]
    return Presentation(io.BytesIO(as_presentation_bytes(data)))


# ---------------------------------------------------------------- extraction
def extract_template(data: bytes, filename: str = "") -> Extraction:
    try:
        prs = open_presentation(data)
    except Exception as error:  # not a zip, or not a presentation
        raise ValueError("That file is not a PowerPoint template. Upload a .potx or .pptx file.") from error
    out = Extraction(name=Path(filename).stem.replace("_", " ").strip() or "Brand kit")
    out.slide_size = (int(prs.slide_width or 12192000), int(prs.slide_height or 6858000))
    master = prs.slide_masters[0]
    theme_xml = _theme_xml(master)
    if theme_xml is not None:
        out.palette = _palette(theme_xml)
        out.fonts = _fonts(theme_xml)
    out.logos = _logos(prs)
    for index, layout in enumerate(master.slide_layouts):
        out.layouts.append({
            "index": index,
            "name": layout.name or f"Layout {index + 1}",
            "placeholders": [_placeholder_kind(ph) for ph in layout.placeholders],
        })
    if not out.palette:
        out.notes.append("The template has no colour scheme, so Lectern's default colours are used.")
    return out


def _theme_xml(master) -> Any:  # type: ignore[no-untyped-def]
    for rel in master.part.rels.values():
        if rel.reltype.endswith("/theme"):
            return etree.fromstring(rel.target_part.blob)
    return None


def _palette(root: Any) -> list[dict[str, str]]:
    scheme = root.find(f".//{A}clrScheme")
    if scheme is None:
        return []
    palette = []
    for slot in SCHEME_SLOTS:
        node = scheme.find(f"{A}{slot}")
        if node is None or not len(node):
            continue
        color = node[0]
        value = color.get("val") if color.tag == f"{A}srgbClr" else color.get("lastClr")
        if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
            palette.append({"slot": slot, "name": SLOT_NAMES[slot], "hex": f"#{value.upper()}"})
    return palette


def _fonts(root: Any) -> dict[str, str]:
    fonts = {}
    for key, tag in (("heading", "majorFont"), ("body", "minorFont")):
        latin = root.find(f".//{A}{tag}/{A}latin")
        if latin is not None and latin.get("typeface") and not latin.get("typeface").startswith("+"):
            fonts[key] = latin.get("typeface")
    return fonts


def _logos(prs) -> list[tuple[bytes, str, int, int]]:  # type: ignore[no-untyped-def]
    """Pictures on the masters and layouts (where logos live), then on slides; largest-first is not useful,
    so keep document order and drop duplicates and full-bleed backgrounds."""
    found: list[tuple[bytes, str, int, int]] = []
    seen: set[bytes] = set()
    sources: list[Any] = []
    for master in prs.slide_masters:
        sources.append(master)
        sources.extend(master.slide_layouts)
    sources.extend(prs.slides)
    width, height = prs.slide_width or 12192000, prs.slide_height or 6858000
    for source in sources:
        for shape in source.shapes:
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            if shape.width > width * 0.6 and shape.height > height * 0.6:
                continue  # a background picture, not a logo
            try:
                image = shape.image
            except Exception:
                continue
            if image.sha1 in seen:  # type: ignore[comparison-overlap]
                continue
            seen.add(image.sha1)  # type: ignore[arg-type]
            px_w = max(1, round(shape.width / 6350))
            px_h = max(1, round(shape.height / 6350))
            found.append((image.blob, image.ext, px_w, px_h))
            if len(found) >= 6:
                return found
    return found


def _placeholder_kind(ph) -> str:  # type: ignore[no-untyped-def]
    try:
        return str(ph.placeholder_format.type).split(".")[-1].split(" ")[0].lower()
    except Exception:
        return "other"


def extract_guide(data: bytes) -> tuple[list[str], list[str], list[str]]:
    """From a brand PDF: hex colours, font names it mentions, and sentences that read like rules."""
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
    except Exception as error:
        raise ValueError("That file is not a readable PDF.") from error
    text = []
    try:
        for n in range(min(len(document), 40)):
            page = document[n]
            text.append(page.get_textpage().get_text_range())
            page.close()
    finally:
        document.close()
    body = "\n".join(text)
    colors = list(dict.fromkeys(f"#{m.upper()}" for m in HEX.findall(body)))
    fonts = list(dict.fromkeys(m.strip() for m in re.findall(
        r"(?:typeface|font)\s*[:\-]\s*([A-Z][A-Za-z0-9 ]{2,30}?)(?=[\.,;\n]|$)", body, flags=re.MULTILINE)))
    sentences = re.split(r"(?<=[.!?])\s+|\n", body)
    rules = []
    for sentence in sentences:
        clean = " ".join(sentence.split())
        if 12 <= len(clean) <= 160 and re.search(r"\b(always|never|must|do not|don't|only|minimum|at least)\b",
                                                 clean, flags=re.IGNORECASE):
            rules.append(clean)
    return colors, fonts, list(dict.fromkeys(rules))[:8]


# ---------------------------------------------------------------- theme
def _rgb(hex_: str) -> tuple[int, int, int]:
    raw = hex_.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb)


def mix(a: str, b: str, t: float) -> str:
    """Blend colour a towards b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))  # type: ignore[arg-type]


def luminance(hex_: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def theme_from(name: str, palette: list[dict[str, str]], fonts: dict[str, str], kit_id: str | None,
               logo: str | None) -> Theme:
    """A slide theme from the template's colour scheme and fonts."""
    slots = {p["slot"]: p["hex"] for p in palette if p.get("slot")}
    base = ThemeColors()
    bg = slots.get("lt1", base.bg)
    ink = slots.get("dk1", base.ink)
    if contrast(bg, ink) < 4.5:  # some templates swap dark and light
        bg, ink = ink, bg
        if contrast(bg, ink) < 4.5:
            bg, ink = base.bg, base.ink
    dk2 = slots.get("dk2")
    body = dk2 if dk2 and contrast(dk2, bg) >= 4.5 else mix(ink, bg, 0.25)
    accent = slots.get("accent1", base.accent)
    accents = [slots[k] for k in ("accent1", "accent2", "accent3", "accent4", "accent5", "accent6") if k in slots]
    on_accent = "#FFFFFF" if contrast(accent, "#FFFFFF") >= contrast(accent, "#16181D") else "#16181D"
    lt2 = slots.get("lt2")
    surface = lt2 if lt2 and contrast(lt2, ink) >= 7 and lt2 != bg else mix(bg, ink, 0.04)
    colors = ThemeColors(bg=bg, ink=ink, body=body, muted=mix(ink, bg, 0.45), line=mix(bg, ink, 0.12),
                         surface=surface, accent=accent, on_accent=on_accent)
    chart = accents or Theme().chart_colors
    return Theme(name=name, font=fonts.get("body") or fonts.get("heading") or "Urbanist", colors=colors,
                 chart_colors=chart, brand_kit_id=kit_id, logo=logo)
