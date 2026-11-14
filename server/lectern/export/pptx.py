"""RenderedSlide -> .pptx with native, editable objects (python-pptx).

Every text element is a live text box, every table a real table, every chart a real PowerPoint
chart with its data sheet. Only `image` elements with a readable source become pictures.
"""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from ..schema import Element, RenderedSlide, Slide, Theme

EMU_PER_PX = 6350            # 12192000 EMU (13.333in) / 1920 px
SLIDE_W = 12192000
SLIDE_H = 6858000
PT_PER_PX = 0.5
MEDIA_SRC = re.compile(r"^(?:https?://[^/]+)?/api/media/(ma_[0-9a-f]{12})/(?:file|poster)$")

_ALIGN = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}
_ANCHOR = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}
_CHART_TYPE = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS,
               "area": XL_CHART_TYPE.AREA, "pie": XL_CHART_TYPE.PIE}


def emu(px: float) -> Emu:
    return Emu(int(round(px * EMU_PER_PX)))


def rgb(color: str | None, fallback: str = "16181D") -> RGBColor:
    value = (color or "").lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        value = fallback
    return RGBColor.from_string(value.upper())


def build_pptx(slides: list[Slide], rendered: list[RenderedSlide], theme: Theme, path: Path,
               include_notes: bool = True, title: str = "", template: Path | None = None) -> Path:
    """Write the deck to `path`. `slides` and `rendered` are parallel lists.
    With `template` (a brand kit's .potx/.pptx) the file is built on that template's master and layouts."""
    master_logo = False
    if template is not None:  # brand kit (U09)
        from ..brand.template import open_template, strip_placeholders
        prs, blank, master_logo = open_template(template)
    else:
        prs = Presentation()
    prs.slide_width = Emu(SLIDE_W)
    prs.slide_height = Emu(SLIDE_H)
    prs.core_properties.title = title
    prs.core_properties.author = "Lectern"
    if template is None:
        blank = prs.slide_layouts[6]
    for slide, drawn in zip(slides, rendered):
        page = prs.slides.add_slide(blank)
        if template is not None:
            strip_placeholders(page)  # the template master shows through: its background and logo
        else:
            fill = page.background.fill
            fill.solid()
            fill.fore_color.rgb = rgb(drawn.background, "FFFFFF")
        for element in drawn.elements:
            if master_logo and element.id == "brand-logo":
                continue
            _add_element(page, element, theme)
        notes = "\n\n".join(part for part in (slide.notes.strip(), *video_notes(slide)) if part)
        if include_notes and notes:
            page.notes_slide.notes_text_frame.text = notes
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return path


def _add_element(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    if element.kind == "text":
        _add_text(page, element, theme)
    elif element.kind == "rect":
        _add_rect(page, element)
    elif element.kind == "line":
        _add_line(page, element, theme)
    elif element.kind == "chart":
        _add_chart(page, element, theme)
    elif element.kind == "table":
        _add_table(page, element, theme)
    elif element.kind == "image":
        _add_image(page, element, theme)


# ---------------------------------------------------------------- text
def _add_text(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    box = page.shapes.add_textbox(emu(element.x), emu(element.y), emu(element.w), emu(element.h))
    box.name = f"Text {element.id}"
    frame = box.text_frame
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
    style = element.style
    frame.vertical_anchor = _ANCHOR.get((style.valign if style else None) or "top", MSO_ANCHOR.TOP)
    size_px = (style.font_size if style else None) or 24
    if element.bullets:
        for n, item in enumerate(element.bullets):
            paragraph = frame.paragraphs[0] if n == 0 else frame.add_paragraph()
            _fill_paragraph(paragraph, item, element, theme)
            _make_bullet(paragraph, size_px)
            if n < len(element.bullets) - 1:
                paragraph.space_after = Pt(size_px * PT_PER_PX * 0.5)
        return
    for n, line in enumerate((element.text or "").split("\n")):
        paragraph = frame.paragraphs[0] if n == 0 else frame.add_paragraph()
        _fill_paragraph(paragraph, line, element, theme)


def _fill_paragraph(paragraph, value: str, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    style = element.style
    paragraph.alignment = _ALIGN.get((style.align if style else None) or "left", PP_ALIGN.LEFT)
    line_height = (style.line_height if style else None) or 1.25
    # PowerPoint measures spacing against the font's own line (about 1.2em), CSS against the em.
    paragraph.line_spacing = max(0.8, round(line_height / 1.2, 2))
    run = paragraph.add_run()
    run.text = value
    font = run.font
    font.name = theme.font
    font.size = Pt(((style.font_size if style else None) or 24) * PT_PER_PX)
    font.bold = bool(style and style.font_weight == 700)
    font.color.rgb = rgb(style.color if style else None)
    properties = run._r.get_or_add_rPr()
    if style and style.uppercase:
        properties.set("cap", "all")
    if style and style.letter_spacing:
        properties.set("spc", str(int(round(style.letter_spacing * PT_PER_PX * 100))))


def _make_bullet(paragraph, size_px: float) -> None:  # type: ignore[no-untyped-def]
    indent = int(round(size_px * 1.1 * EMU_PER_PX))
    properties = paragraph._p.get_or_add_pPr()
    properties.set("marL", str(indent))
    properties.set("indent", str(-indent))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont"):
        for old in properties.findall(qn(tag)):
            properties.remove(old)
    font = etree.SubElement(properties, qn("a:buFont"))
    font.set("typeface", "Arial")
    char = etree.SubElement(properties, qn("a:buChar"))
    char.set("char", "•")


# ---------------------------------------------------------------- shapes
def _add_rect(page, element: Element) -> None:  # type: ignore[no-untyped-def]
    style = element.style
    radius = (style.radius if style else None) or 0
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = page.shapes.add_shape(kind, emu(element.x), emu(element.y), emu(element.w), emu(element.h))
    shape.name = f"Shape {element.id}"
    if radius:
        shape.adjustments[0] = min(0.5, radius / max(1.0, min(element.w, element.h)))
    shape.shadow.inherit = False
    if style and style.fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = rgb(style.fill)
    else:
        shape.fill.background()
    if style and style.stroke:
        shape.line.color.rgb = rgb(style.stroke)
        shape.line.width = emu(style.stroke_width or 1)
    else:
        shape.line.fill.background()


def _add_line(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    style = element.style
    horizontal = element.w >= element.h
    x2 = element.x + element.w if horizontal else element.x
    y2 = element.y if horizontal else element.y + element.h
    line = page.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, emu(element.x), emu(element.y), emu(x2), emu(y2))
    line.name = f"Line {element.id}"
    line.line.color.rgb = rgb((style.stroke if style else None) or theme.colors.line)
    line.line.width = emu((style.stroke_width if style else None) or 2)


# ---------------------------------------------------------------- chart
def _number_format(unit: str | None, values: list[float]) -> str:
    decimals = "0.0" if any(abs(v - round(v)) > 1e-9 for v in values) else "0"
    grouped = f"#,##{decimals}"
    peak = max((abs(v) for v in values), default=0.0)
    # Millions read as "$3.2M", not "$3,230,000" (which some locales group as "$32,30,000").
    for size, commas, suffix, places in ((1e9, ",,,", "B", "00"), (1e6, ",,", "M", "00"), (1e4, ",", "k", "0")):
        if peak >= size:
            grouped = f'#,##0.{places}{commas}"{suffix}"'
            break
    unit = (unit or "").strip()
    if not unit:
        return grouped
    if unit in {"$", "€", "£", "₹"}:
        return f'"{unit}"{grouped}'
    return f'{grouped}"{unit}"'


def _add_chart(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    spec = element.chart
    if spec is None:
        return
    data = CategoryChartData()
    data.categories = list(spec.categories)
    count = len(spec.categories)
    all_values: list[float] = []
    for series in spec.series:
        values = [float(v) for v in series.values[:count]] + [0.0] * max(0, count - len(series.values))
        all_values.extend(values)
        data.add_series(series.name, values)
    number_format = _number_format(spec.unit, all_values)
    frame = page.shapes.add_chart(_CHART_TYPE.get(spec.kind, XL_CHART_TYPE.COLUMN_CLUSTERED),
                                  emu(element.x), emu(element.y), emu(element.w), emu(element.h), data)
    frame.name = f"Chart {element.id}"
    chart = frame.chart
    font_pt = ((element.style.font_size if element.style else None) or 22) * PT_PER_PX
    chart.font.size = Pt(font_pt)
    chart.font.name = theme.font
    chart.font.color.rgb = rgb(theme.colors.body)
    chart.has_title = False
    multi = len(spec.series) > 1
    chart.has_legend = multi or spec.kind == "pie"
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(font_pt)
    plot = chart.plots[0]
    colors = spec.colors or theme.chart_colors
    if spec.kind == "pie":
        points = plot.series[0].points
        for n in range(count):
            fill = points[n].format.fill
            fill.solid()
            fill.fore_color.rgb = rgb(colors[n % len(colors)])
    else:
        for n, series in enumerate(plot.series):
            color = rgb(colors[n % len(colors)])
            if spec.kind == "line":
                series.format.line.color.rgb = color
                series.format.line.width = Pt(3)
                series.smooth = False
                series.marker.format.fill.solid()
                series.marker.format.fill.fore_color.rgb = color
                series.marker.format.line.color.rgb = color
            else:
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = color
        value_axis = chart.value_axis
        value_axis.has_major_gridlines = True
        value_axis.major_gridlines.format.line.color.rgb = rgb(theme.colors.line)
        value_axis.format.line.fill.background()
        value_axis.tick_labels.number_format = number_format
        value_axis.tick_labels.number_format_is_linked = False
        value_axis.tick_labels.font.size = Pt(font_pt)
        chart.category_axis.format.line.color.rgb = rgb(theme.colors.line)
        chart.category_axis.tick_labels.font.size = Pt(font_pt)
        if spec.kind == "bar":
            plot.gap_width = 80 if count <= 3 else 60
            plot.overlap = -10 if multi else 0
    if spec.kind == "pie" or count * len(spec.series) <= 12:
        plot.has_data_labels = True
        labels = plot.data_labels
        labels.number_format = number_format
        labels.number_format_is_linked = False
        labels.font.size = Pt(font_pt)
        labels.font.bold = True
        labels.font.color.rgb = rgb(theme.colors.ink)
        if spec.kind == "line":  # centred labels sit on the line and its markers
            labels.position = XL_LABEL_POSITION.ABOVE


# ---------------------------------------------------------------- table
def _add_table(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    spec = element.table
    if spec is None or not spec.columns:
        return
    rows, cols = len(spec.rows) + 1, len(spec.columns)
    frame = page.shapes.add_table(rows, cols, emu(element.x), emu(element.y), emu(element.w), emu(element.h))
    frame.name = f"Table {element.id}"
    table = frame.table
    table.first_row = True
    table.horz_banding = False
    size_pt = ((element.style.font_size if element.style else None) or 24) * PT_PER_PX
    row_height = int(round(element.h * EMU_PER_PX / rows))
    for r in range(rows):
        table.rows[r].height = Emu(row_height)
        values = spec.columns if r == 0 else spec.rows[r - 1]
        for c in range(cols):
            cell = table.cell(r, c)
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = rgb(theme.colors.ink)
            else:
                cell.fill.fore_color.rgb = rgb(theme.colors.surface if r % 2 == 0 else theme.colors.bg, "FFFFFF")
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = emu(16)
            cell.margin_top = cell.margin_bottom = emu(8)
            frame_ = cell.text_frame
            frame_.word_wrap = True
            paragraph = frame_.paragraphs[0]
            run = paragraph.add_run()
            run.text = str(values[c]) if c < len(values) else ""
            run.font.name = theme.font
            run.font.size = Pt(size_pt)
            run.font.bold = r == 0 or c == 0
            run.font.color.rgb = rgb("#FFFFFF" if r == 0 else theme.colors.ink)


# ---------------------------------------------------------------- image
def video_notes(slide: Slide) -> list[str]:
    """A note per video on the slide: PowerPoint gets its poster frame as the picture."""
    from ..media.router import get_asset

    notes = []
    for node in slide.nodes:
        asset_id = getattr(node, "asset_id", None) if node.type == "image" else None
        if not asset_id:
            continue
        try:
            row = get_asset(asset_id)
        except Exception:
            continue
        if row.kind == "video":
            notes.append(f"Video: this picture is the poster frame of a video made in Lectern "
                         f"(\"{row.prompt[:120]}\"). Insert the video file {row.path.split('/')[-1]} from "
                         "Lectern's media library to play it in PowerPoint.")
    return notes


def _image_bytes(src: str) -> bytes | None:
    """Bytes for a data URI or a local file. Remote URLs are not fetched: the export stays offline."""
    if src.startswith("data:"):
        try:
            return base64.b64decode(src.split(",", 1)[1])
        except (IndexError, ValueError):
            return None
    asset = MEDIA_SRC.match(src)
    if asset:
        from ..media.router import picture_path
        path = picture_path(asset.group(1))
        return path.read_bytes() if path else None
    if re.match(r"^https?://", src):
        return None
    try:
        return Path(src).read_bytes()
    except OSError:
        return None


def _add_image(page, element: Element, theme: Theme) -> None:  # type: ignore[no-untyped-def]
    data = _image_bytes(element.src or "")
    if data:
        try:
            picture = page.shapes.add_picture(io.BytesIO(data), emu(element.x), emu(element.y), emu(element.w),
                                              emu(element.h))
            picture.name = f"Picture {element.id}"
            if element.alt:
                picture._element.nvPicPr.cNvPr.set("descr", element.alt[:250])
            return
        except Exception:  # unreadable image data: fall through to the placeholder
            pass
    shape = page.shapes.add_shape(MSO_SHAPE.RECTANGLE, emu(element.x), emu(element.y), emu(element.w),
                                  emu(element.h))
    shape.name = f"Image placeholder {element.id}"
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(theme.colors.surface)
    shape.line.color.rgb = rgb(theme.colors.line)
    frame = shape.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = element.alt or "Image"
    run.font.name = theme.font
    run.font.size = Pt(12)
    run.font.color.rgb = rgb(theme.colors.body)
