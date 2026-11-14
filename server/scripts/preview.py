"""Developer aid: draw rendered slides to a PNG contact sheet (Arial stands in for Urbanist).

    uv run python scripts/preview.py out.png            # the sample slide for every layout
    uv run python scripts/preview.py out.png DECK_ID    # a deck from the local database

Charts and tables are drawn as outlined placeholders; this is for checking placement, not styling.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lectern.engine import text as tx  # noqa: E402
from lectern.engine.place import place_deck  # noqa: E402
from lectern.schema import RenderedSlide  # noqa: E402


def _font(size: float, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", int(size))
    except OSError:
        return ImageFont.load_default()


def draw_slide(rendered: RenderedSlide, scale: float = 0.5) -> Image.Image:
    image = Image.new("RGB", (1920, 1080), rendered.background)
    draw = ImageDraw.Draw(image)
    for e in rendered.elements:
        style = e.style
        box = [e.x, e.y, e.x + e.w, e.y + e.h]
        if e.kind == "rect" and style:
            draw.rounded_rectangle(box, radius=style.radius or 0, fill=style.fill, outline=style.stroke,
                                   width=int(style.stroke_width or 1))
        elif e.kind in ("chart", "table", "image"):
            draw.rectangle(box, outline="#0E8F8E", width=3)
            draw.text((e.x + 8, e.y + 8), e.kind.upper(), fill="#0E8F8E", font=_font(24, True))
        elif e.kind == "text" and style and style.font_size:
            size = style.font_size
            bold = style.font_weight == 700
            font = _font(size, bold)
            line_h = (style.line_height or 1.25) * size
            lines: list[str | None] = []
            if e.bullets:
                for bullet in e.bullets:
                    wrapped = tx.wrap(bullet, size, e.w - tx.BULLET_INDENT_EM * size)
                    lines += [("• " if i == 0 else "   ") + line for i, line in enumerate(wrapped)] + [None]
                lines = lines[:-1]
            else:
                value = (e.text or "").upper() if style.uppercase else (e.text or "")
                lines = list(tx.wrap(value, size, e.w, bold, style.letter_spacing or 0, bool(style.uppercase)))
            total = sum(line_h if line is not None else size * tx.BULLET_GAP_EM for line in lines)
            y = e.y + ((e.h - total) / 2 if style.valign == "middle" else (e.h - total)
                       if style.valign == "bottom" else 0)
            for line in lines:
                if line is None:
                    y += size * tx.BULLET_GAP_EM
                    continue
                width = draw.textlength(line, font=font)
                x = e.x + ((e.w - width) / 2 if style.align == "center" else (e.w - width)
                           if style.align == "right" else 0)
                draw.text((x, y + (line_h - size) / 2), line, fill=style.color, font=font)
                y += line_h
    return image.resize((int(1920 * scale), int(1080 * scale)))


def sheet(rendered: list[RenderedSlide], path: str, cols: int = 3, scale: float = 0.33) -> None:
    images = [draw_slide(r, scale) for r in rendered]
    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    out = Image.new("RGB", (cols * (w + 8), rows * (h + 8)), "#9A9AA0")
    for i, image in enumerate(images):
        out.paste(image, ((i % cols) * (w + 8), (i // cols) * (h + 8)))
    out.save(path)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
    which = sys.argv[2] if len(sys.argv) > 2 else None
    if which in (None, "stress"):
        from tests import samples
        slides = samples.stress_layouts() if which == "stress" else samples.all_layouts()
        theme = None
    else:
        from lectern import store
        from lectern.db import init_db
        init_db()
        deck = store.load_deck(which)
        slides, theme = deck.slides, deck.theme
    rendered = place_deck(slides, theme)
    half = (len(rendered) + 1) // 2 if len(rendered) > 12 else len(rendered)
    stem = Path(target)
    if half < len(rendered):
        sheet(rendered[:half], str(stem.with_name(stem.stem + "-1" + stem.suffix)))
        sheet(rendered[half:], str(stem.with_name(stem.stem + "-2" + stem.suffix)))
    else:
        sheet(rendered, target)
    print(f"wrote {target} ({len(rendered)} slides)")


if __name__ == "__main__":
    main()
