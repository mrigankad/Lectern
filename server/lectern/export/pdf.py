"""RenderedSlide -> vector PDF (reportlab), PNG per slide (pdfium) and speaker notes (Markdown).

The PDF is drawn from the same RenderedSlide data as the canvas and the .pptx: text is real text in an
embedded font, charts and tables are vector paths, pictures are embedded. One page is 960 x 540 pt
(16:9, 1 canvas px = 0.5 pt, the same scale as the PowerPoint export).
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from functools import lru_cache
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from ..schema import Element, ExportReport, RenderedSlide, Slide, Theme

W, H = 1920, 1080
PAGE = (W * 0.5, H * 0.5)
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
URBANIST = ("Urbanist", "Urbanist-Bold")


# ---------------------------------------------------------------- fonts
@lru_cache(maxsize=1)
def _register_urbanist() -> tuple[str, str]:
    pdfmetrics.registerFont(TTFont("Urbanist", str(FONTS_DIR / "Urbanist-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Urbanist-Bold", str(FONTS_DIR / "Urbanist-Bold.ttf")))
    return URBANIST


def _font_files(family: str, extra_dirs: tuple[Path, ...]) -> tuple[Path | None, Path | None]:
    """Regular and bold TrueType files for a family name, from brand-kit fonts or the system fonts."""
    key = re.sub(r"[^a-z0-9]", "", family.lower())
    if not key:
        return None, None
    dirs = [*extra_dirs, Path("C:/Windows/Fonts"), Path("/usr/share/fonts"), Path("/Library/Fonts")]
    regular = bold = None
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.ttf"):
            stem = re.sub(r"[^a-z0-9]", "", path.stem.lower())
            if stem in {key, f"{key}regular"} and regular is None:
                regular = path
            elif stem in {f"{key}bold", f"{key}bd", f"{key}b"} and bold is None:
                bold = path
        if regular:
            break
    return regular, bold


@lru_cache(maxsize=32)
def _fonts_for(family: str, extra_dirs: tuple[Path, ...] = ()) -> tuple[str, str]:
    """Registered (regular, bold) font names for the theme font, falling back to bundled Urbanist."""
    urbanist = _register_urbanist()
    if not family or family.lower() == "urbanist":
        return urbanist
    regular, bold = _font_files(family, extra_dirs)
    if regular is None:
        return urbanist
    try:
        name = f"Theme-{re.sub(r'[^A-Za-z0-9]', '', family)}"
        pdfmetrics.registerFont(TTFont(name, str(regular)))
        bold_name = name
        if bold is not None:
            pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold)))
            bold_name = f"{name}-Bold"
        return name, bold_name
    except Exception:  # an unreadable or PostScript-flavoured font: keep the bundled one
        return urbanist


# ---------------------------------------------------------------- helpers
def _color(value: str | None, fallback: str = "#16181D") -> HexColor:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", raw):
        raw = fallback.lstrip("#")
    return HexColor("#" + raw)


def _wrap(text: str, font: str, size: float, width: float, spacing: float) -> list[str]:
    def measure(s: str) -> float:
        return pdfmetrics.stringWidth(s, font, size) + spacing * len(s)

    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            if measure(f"{current} {word}") <= width + 0.5:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fmt(value: float, unit: str | None, peak: float = 0.0) -> str:
    """A chart number; `peak` (the chart's largest value) picks one scale for the whole chart, as the
    PowerPoint export does: $3.23M rather than $3,230,000."""
    for size, suffix, places in ((1e9, "B", 2), (1e6, "M", 2), (1e4, "k", 1)):
        if max(abs(peak), abs(value)) >= size:
            text = f"{value / size:,.{places}f}{suffix}"
            break
    else:
        text = f"{value:,.1f}" if abs(value - round(value)) > 1e-9 else f"{int(round(value)):,}"
    unit = (unit or "").strip()
    if unit in {"$", "€", "£", "₹"}:
        return unit + text
    return text + unit


class _Painter:
    """Draws RenderedSlide elements in canvas px with y measured from the top."""

    def __init__(self, c: Canvas, theme: Theme, fonts: tuple[str, str]):
        self.c = c
        self.theme = theme
        self.regular, self.bold = fonts
        self._peak = 0.0

    def y(self, y: float) -> float:
        return H - y

    # ---------------------------------------------------------- slide
    def slide(self, drawn: RenderedSlide) -> None:
        c = self.c
        c.setFillColor(_color(drawn.background, "#FFFFFF"))
        c.rect(0, 0, W, H, stroke=0, fill=1)
        for element in drawn.elements:
            c.saveState()
            try:
                getattr(self, f"_{element.kind}")(element)
            finally:
                c.restoreState()

    # ---------------------------------------------------------- text
    def text_block(self, x: float, y: float, w: float, h: float, text: str | None, bullets: list[str] | None,
                   size: float, bold: bool, color: str | None, align: str, valign: str, line_height: float,
                   uppercase: bool = False, letter_spacing: float = 0.0) -> None:
        c = self.c
        font = self.bold if bold else self.regular
        spacing = letter_spacing * size if 0 < letter_spacing < 1 else letter_spacing
        line_h = size * line_height
        indent = size * 1.1 if bullets else 0.0
        paragraphs = bullets if bullets else [text or ""]
        laid: list[tuple[float, str, bool]] = []  # (top offset, line, first line of a bullet)
        cursor = 0.0
        for n, paragraph in enumerate(paragraphs):
            value = paragraph.upper() if uppercase else paragraph
            for k, line in enumerate(_wrap(value, font, size, w - indent, spacing)):
                laid.append((cursor, line, k == 0))
                cursor += line_h
            if bullets and n < len(paragraphs) - 1:
                cursor += size * 0.5
        total = cursor
        top = y if valign == "top" else y + (h - total) / 2 if valign == "middle" else y + h - total
        c.setFillColor(_color(color))
        ascent = size * 0.78 + (line_h - size) / 2
        for offset, line, first in laid:
            baseline = self.y(top + offset + ascent)
            if bullets and first:
                c.setFont(self.regular, size)
                c.drawString(x, baseline, "•")
            line_w = pdfmetrics.stringWidth(line, font, size) + spacing * len(line)
            left = x + indent
            if align == "center":
                left = x + indent + (w - indent - line_w) / 2
            elif align == "right":
                left = x + w - line_w
            obj = c.beginText(left, baseline)
            obj.setFont(font, size)
            if spacing:
                obj.setCharSpace(spacing)
            obj.textOut(line)
            c.drawText(obj)

    def _text(self, e: Element) -> None:
        s = e.style
        self.text_block(e.x, e.y, e.w, e.h, e.text, e.bullets, (s.font_size if s else None) or 24,
                        bool(s and s.font_weight == 700), s.color if s else None,
                        (s.align if s else None) or "left", (s.valign if s else None) or "top",
                        (s.line_height if s else None) or 1.25, bool(s and s.uppercase),
                        (s.letter_spacing if s else None) or 0.0)

    # ---------------------------------------------------------- shapes
    def _rect(self, e: Element) -> None:
        s = e.style
        fill = bool(s and s.fill)
        stroke = bool(s and s.stroke)
        if not fill and not stroke:
            return
        c = self.c
        if fill:
            c.setFillColor(_color(s.fill))  # type: ignore[union-attr]
        if stroke:
            c.setStrokeColor(_color(s.stroke))  # type: ignore[union-attr]
            c.setLineWidth(s.stroke_width or 1)  # type: ignore[union-attr]
        radius = min((s.radius if s else None) or 0, e.w / 2, e.h / 2)
        if radius:
            c.roundRect(e.x, self.y(e.y + e.h), e.w, e.h, radius, stroke=int(stroke), fill=int(fill))
        else:
            c.rect(e.x, self.y(e.y + e.h), e.w, e.h, stroke=int(stroke), fill=int(fill))

    def _line(self, e: Element) -> None:
        s = e.style
        c = self.c
        c.setStrokeColor(_color((s.stroke if s else None) or self.theme.colors.line))
        c.setLineWidth((s.stroke_width if s else None) or 2)
        if e.w >= e.h:
            c.line(e.x, self.y(e.y), e.x + e.w, self.y(e.y))
        else:
            c.line(e.x, self.y(e.y), e.x, self.y(e.y + e.h))

    # ---------------------------------------------------------- image
    def _image(self, e: Element) -> None:
        from .pptx import _image_bytes

        c = self.c
        data = _image_bytes(e.src or "")
        if data:
            try:
                reader = ImageReader(io.BytesIO(data))
                iw, ih = reader.getSize()
                # cover-fit like the canvas, clipped to the box
                scale = max(e.w / iw, e.h / ih)
                dw, dh = iw * scale, ih * scale
                path = c.beginPath()
                path.rect(e.x, self.y(e.y + e.h), e.w, e.h)
                c.clipPath(path, stroke=0, fill=0)
                c.drawImage(reader, e.x + (e.w - dw) / 2, self.y(e.y + (e.h + dh) / 2), dw, dh, mask="auto")
                return
            except Exception:
                pass
        c.setFillColor(_color(self.theme.colors.surface))
        c.setStrokeColor(_color(self.theme.colors.line))
        c.rect(e.x, self.y(e.y + e.h), e.w, e.h, stroke=1, fill=1)
        self.text_block(e.x + 16, e.y, e.w - 32, e.h, e.alt or "Image", None, 24, False, self.theme.colors.body,
                        "center", "middle", 1.25)

    # ---------------------------------------------------------- table
    def _table(self, e: Element) -> None:
        spec = e.table
        if spec is None or not spec.columns:
            return
        c = self.c
        colors = self.theme.colors
        size = (e.style.font_size if e.style else None) or 24
        rows = [spec.columns, *spec.rows]
        row_h = e.h / len(rows)
        col_w = e.w / len(spec.columns)
        for r, values in enumerate(rows):
            top = e.y + r * row_h
            fill = colors.ink if r == 0 else colors.surface if r % 2 == 0 else colors.bg
            c.setFillColor(_color(fill, "#FFFFFF"))
            c.rect(e.x, self.y(top + row_h), e.w, row_h, stroke=0, fill=1)
            for k in range(len(spec.columns)):
                value = str(values[k]) if k < len(values) else ""
                self.text_block(e.x + k * col_w + 16, top + 8, col_w - 32, row_h - 16, value, None, size,
                                r == 0 or k == 0, "#FFFFFF" if r == 0 else colors.ink, "left", "middle", 1.2)

    # ---------------------------------------------------------- chart
    def _chart(self, e: Element) -> None:
        spec = e.chart
        if spec is None or not spec.categories or not spec.series:
            return
        c = self.c
        size = (e.style.font_size if e.style else None) or 22
        palette = spec.colors or self.theme.chart_colors or ["#2563EB"]
        colors = self.theme.colors
        legend = len(spec.series) > 1 or spec.kind == "pie"
        legend_h = size * 2.2 if legend else 0
        names = spec.categories if spec.kind == "pie" else [s.name for s in spec.series]
        if legend:
            self._legend(e.x, e.y + e.h - legend_h, e.w, legend_h, names, palette, size)
        self._peak = max((abs(float(v)) for s in spec.series for v in s.values), default=0.0)
        if spec.kind == "pie":
            self._pie(e, e.h - legend_h, palette, size)
            return
        count = len(spec.categories)
        values = [[float(v) for v in s.values[:count]] + [0.0] * max(0, count - len(s.values)) for s in spec.series]
        flat = [v for row in values for v in row] or [0.0]
        high, low = max(max(flat), 0.0), min(min(flat), 0.0)
        step = _nice_step((high - low) or 1.0)
        high = math.ceil(high / step) * step if high > 0 else 0.0
        low = math.floor(low / step) * step if low < 0 else 0.0
        if high == low:
            high = low + step
        labels = [_fmt(low + k * step, spec.unit, self._peak) for k in range(int(round((high - low) / step)) + 1)]
        axis_w = max(pdfmetrics.stringWidth(t, self.regular, size) for t in labels) + 16
        left, right = e.x + axis_w, e.x + e.w
        top, bottom = e.y + size, e.y + e.h - legend_h - size * 1.8

        def ypos(v: float) -> float:
            return bottom - (v - low) / (high - low) * (bottom - top)

        c.setLineWidth(1.5)
        for k, label in enumerate(labels):
            gy = ypos(low + k * step)
            c.setStrokeColor(_color(colors.line))
            c.line(left, self.y(gy), right, self.y(gy))
            c.setFillColor(_color(colors.body))
            c.setFont(self.regular, size)
            c.drawRightString(left - 12, self.y(gy + size * 0.35), label)
        band = (right - left) / count
        show_values = count * len(spec.series) <= 12
        for k, cat in enumerate(spec.categories):
            c.setFillColor(_color(colors.body))
            c.setFont(self.regular, size)
            cx = left + band * (k + 0.5)
            c.drawCentredString(cx, self.y(bottom + size * 1.3), _clip(cat, self.regular, size, band - 6))
        if spec.kind == "bar":
            n = len(values)
            group = band * (0.62 if count > 3 else 0.55)
            bar = group / n
            for si, row in enumerate(values):
                c.setFillColor(_color(palette[si % len(palette)]))
                for k, v in enumerate(row):
                    x0 = left + band * k + (band - group) / 2 + si * bar
                    y0, y1 = sorted((ypos(v), ypos(0)))
                    c.rect(x0 + 2, self.y(y1), bar - 4, y1 - y0, stroke=0, fill=1)
                    if show_values:
                        self._value_label(x0 + bar / 2, y0 - size * 0.4, _fmt(v, spec.unit, self._peak), size)
            return
        for si, row in enumerate(values):
            color = _color(palette[si % len(palette)])
            points = [(left + band * (k + 0.5), ypos(v)) for k, v in enumerate(row)]
            if spec.kind == "area":
                path = c.beginPath()
                path.moveTo(points[0][0], self.y(ypos(0)))
                for px, py in points:
                    path.lineTo(px, self.y(py))
                path.lineTo(points[-1][0], self.y(ypos(0)))
                path.close()
                c.setFillColor(color, alpha=0.85 if len(values) == 1 else 0.6)
                c.drawPath(path, stroke=0, fill=1)
            else:
                c.setStrokeColor(color)
                c.setLineWidth(6)
                c.setLineJoin(1)
                path = c.beginPath()
                path.moveTo(points[0][0], self.y(points[0][1]))
                for px, py in points[1:]:
                    path.lineTo(px, self.y(py))
                c.drawPath(path, stroke=1, fill=0)
                c.setFillColor(color)
                for px, py in points:
                    c.circle(px, self.y(py), 9, stroke=0, fill=1)
            if show_values:
                for (px, py), v in zip(points, row):
                    self._value_label(px, py - size * 0.7, _fmt(v, spec.unit, self._peak), size)

    def _value_label(self, cx: float, baseline_top: float, text: str, size: float) -> None:
        self.c.setFillColor(_color(self.theme.colors.ink))
        self.c.setFont(self.bold, size)
        self.c.drawCentredString(cx, self.y(baseline_top), text)

    def _legend(self, x: float, y: float, w: float, h: float, names: list[str], palette: list[str],
                size: float) -> None:
        c = self.c
        widths = [size * 1.4 + pdfmetrics.stringWidth(n, self.regular, size) + size * 1.4 for n in names]
        cursor = x + max(0.0, (w - sum(widths)) / 2)
        base = y + h / 2
        for n, (name, width) in enumerate(zip(names, widths)):
            c.setFillColor(_color(palette[n % len(palette)]))
            c.roundRect(cursor, self.y(base + size * 0.4), size * 0.8, size * 0.8, 3, stroke=0, fill=1)
            c.setFillColor(_color(self.theme.colors.body))
            c.setFont(self.regular, size)
            c.drawString(cursor + size * 1.2, self.y(base + size * 0.35), name)
            cursor += width

    def _pie(self, e: Element, height: float, palette: list[str], size: float) -> None:
        c = self.c
        spec = e.chart
        assert spec is not None
        values = [max(0.0, float(v)) for v in spec.series[0].values[:len(spec.categories)]]
        total = sum(values) or 1.0
        r = min(e.w, height) / 2 - size
        cx, cy = e.x + e.w / 2, e.y + height / 2
        angle = 90.0
        for n, v in enumerate(values):
            extent = -360.0 * v / total
            if abs(extent) < 1e-6:
                continue
            c.setFillColor(_color(palette[n % len(palette)]))
            c.setStrokeColor(_color(self.theme.colors.bg, "#FFFFFF"))
            c.setLineWidth(3)
            if abs(extent) >= 359.999:
                c.circle(cx, self.y(cy), r, stroke=0, fill=1)
            else:
                c.wedge(cx - r, self.y(cy) - r, cx + r, self.y(cy) + r, angle, extent, stroke=1, fill=1)
            if spec.categories and len(values) <= 8:
                mid = math.radians(angle + extent / 2)
                lx, ly = cx + math.cos(mid) * r * 0.65, cy - math.sin(mid) * r * 0.65
                c.setFillColor(_color("#FFFFFF"))
                c.setFont(self.bold, size)
                c.drawCentredString(lx, self.y(ly + size * 0.35), _fmt(v, spec.unit, self._peak))
            angle += extent


def _nice_step(span: float) -> float:
    raw = span / 4
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * power:
            return mult * power
    return 10 * power


def _clip(text: str, font: str, size: float, width: float) -> str:
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


# ---------------------------------------------------------------- entry points
def build_pdf(slides: list[Slide], rendered: list[RenderedSlide], theme: Theme, path: Path,
              include_notes: bool = False, title: str = "", font_dirs: tuple[Path, ...] = ()) -> Path:
    """Write one 16:9 page per slide; with `include_notes`, each slide is followed by a notes page."""
    from .pptx import video_notes

    path.parent.mkdir(parents=True, exist_ok=True)
    fonts = _fonts_for(theme.font, font_dirs)
    c = Canvas(str(path), pagesize=PAGE, pageCompression=1)
    c.setTitle(title or "Deck")
    c.setAuthor("Lectern")
    c.setCreator("Lectern")
    painter = _Painter(c, theme, fonts)
    for slide, drawn in zip(slides, rendered):
        c.saveState()
        c.scale(0.5, 0.5)
        painter.slide(drawn)
        c.restoreState()
        c.showPage()
        if include_notes:
            notes = "\n\n".join(p for p in (slide.notes.strip(), *video_notes(slide)) if p)
            _notes_page(c, painter, slide, drawn, notes)
            c.showPage()
    c.save()
    return path


def _notes_page(c: Canvas, painter: _Painter, slide: Slide, drawn: RenderedSlide, notes: str) -> None:
    """Slide thumbnail on the left, notes on the right, on the same 16:9 page size."""
    c.saveState()
    c.scale(0.5, 0.5)
    c.setFillColor(_color("#FFFFFF"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.restoreState()
    c.saveState()
    # thumbnail: 40% scale, 64px margin (in canvas px, page scale 0.5)
    c.translate(32, PAGE[1] - 32 - H * 0.2)
    c.scale(0.2, 0.2)
    painter.slide(drawn)
    c.setStrokeColor(_color("#D9D9E0"))
    c.setLineWidth(4)
    c.rect(0, 0, W, H, stroke=1, fill=0)
    c.restoreState()
    c.saveState()
    c.scale(0.5, 0.5)
    painter.text_block(64, 64 + H * 0.4 + 40, W * 0.4, 60, f"Slide {slide.index}", None, 24, True, "#7A7F8C",
                       "left", "top", 1.2)
    painter.text_block(64, 64 + H * 0.4 + 80, W * 0.4, 200, slide.headline, None, 32, True, "#16181D",
                       "left", "top", 1.25)
    painter.text_block(W * 0.4 + 128, 64, W * 0.6 - 192, H - 128, notes or "No speaker notes for this slide.",
                       None, 30, False, "#5E6370" if not notes else "#16181D", "left", "top", 1.45)
    c.restoreState()


def build_images(pdf_path: Path, zip_path: Path, stem: str, scale: float = 2.0) -> tuple[Path, int]:
    """Rasterise each page of a slides-only PDF to PNG (960pt x 2 = 1920x1080) and zip them."""
    import pypdfium2 as pdfium

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    count = len(document)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for n in range(count):
                page = document[n]
                image = page.render(scale=scale).to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                archive.writestr(f"{stem} - slide {n + 1:02d}.png", buffer.getvalue())
                page.close()
    finally:
        document.close()
    return zip_path, count


def build_notes_markdown(slides: list[Slide], title: str, path: Path) -> Path:
    """Speaker notes as a Markdown script: one section per slide."""
    from .pptx import video_notes

    lines = [f"# {title or 'Deck'}: speaker notes", ""]
    for slide in slides:
        heading = f"## {slide.index}. {slide.headline.strip()}"
        if slide.section:
            heading += f"  \n*{slide.section}*"
        lines += [heading, ""]
        notes = "\n\n".join(p for p in (slide.notes.strip(), *video_notes(slide)) if p)
        lines += [notes or "_No notes for this slide._", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def file_report(fmt: str, rendered: list[RenderedSlide], slides: list[Slide], theme: Theme,
                include_notes: bool) -> ExportReport:
    """The export report for the non-PowerPoint formats: what was drawn and how."""
    from ..schema import Check

    kinds = [e.kind for r in rendered for e in r.elements]
    charts, tables, pictures = kinds.count("chart"), kinds.count("table"), kinds.count("image")
    text_boxes = kinds.count("text")
    with_notes = sum(1 for s in slides if s.notes.strip())
    font = theme.font if _fonts_for(theme.font) != URBANIST or theme.font.lower() == "urbanist" else "Urbanist"
    checks: list[Check] = []
    if fmt == "pdf":
        checks = [
            Check(label="Vector pages", ok=True, detail=f"{len(rendered)} pages at 16:9; text, charts and tables "
                  "are vector, so they stay sharp at any zoom."),
            Check(label="Fonts embedded", ok=True, detail=f"{font} is embedded, so the file looks the same "
                  "on any computer."),
            Check(label="Selectable text", ok=True, detail="Text can be searched and copied."),
            Check(label="Speaker notes", ok=not include_notes or with_notes == len(slides),
                  detail=(f"A notes page follows each slide ({with_notes} of {len(slides)} slides have notes)."
                          if include_notes else "Not included.")),
        ]
        if font != theme.font:
            checks.append(Check(label="Theme font", ok=False, detail=f"{theme.font} was not found on this "
                                "computer, so the PDF uses Urbanist."))
    elif fmt == "images":
        checks = [Check(label="One PNG per slide", ok=True, detail=f"{len(rendered)} images at 1920 x 1080 in a zip."),
                  Check(label="Not editable", ok=True, detail="Images are flat pictures; use PowerPoint to edit.")]
    else:
        checks = [Check(label="Speaker notes", ok=with_notes == len(slides),
                        detail=f"{with_notes} of {len(slides)} slides have notes, in slide order, as Markdown.")]
    drawn = len(kinds) if fmt != "notes" else 0
    return ExportReport(total_objects=drawn, editable_objects=0 if fmt in ("images", "notes") else drawn - pictures,
                        pictures=drawn if fmt == "images" else 0 if fmt == "notes" else pictures, charts=charts, tables=tables,
                        text_boxes=text_boxes, notes_slides=with_notes if include_notes or fmt == "notes" else 0,
                        checks=checks)
