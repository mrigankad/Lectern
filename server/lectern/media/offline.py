"""Offline media: deterministic, flat placeholder illustrations drawn with PIL in the deck's colours.

No network and no keys, so media works out of the box and in tests. The same prompt, aspect and
theme always give the same picture.
"""
from __future__ import annotations

import hashlib
import io
import random

from PIL import Image, ImageDraw

from ..schema import ThemeColors
from .base import Kind, MediaResult, require_kind, size_of

DATA_WORDS = ("growth", "revenue", "chart", "data", "metric", "churn", "sales", "market", "budget", "%", "kpi")
PEOPLE_WORDS = ("team", "people", "customer", "user", "hire", "staff", "client", "audience")


def _hex(color: str, fallback: str) -> tuple[int, int, int]:
    value = (color or fallback).lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return _hex(fallback, "#2563EB")


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def draw(prompt: str, aspect: str, colors: ThemeColors | None = None) -> bytes:
    colors = colors or ThemeColors()
    width, height = size_of(aspect)
    seed = int(hashlib.sha256(f"{prompt}|{aspect}|{colors.accent}".encode()).hexdigest()[:12], 16)
    rnd = random.Random(seed)
    bg = _hex(colors.surface, "#F7F7F8")
    accent = _hex(colors.accent, "#2563EB")
    ink = _hex(colors.ink, "#16181D")
    soft = _mix(accent, (255, 255, 255), 0.82)
    mid = _mix(accent, (255, 255, 255), 0.5)
    image = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(image)
    unit = min(width, height)
    # soft background shapes
    for _ in range(3):
        r = rnd.uniform(0.25, 0.45) * unit
        cx, cy = rnd.uniform(0, width), rnd.uniform(0, height)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=soft)
    text = prompt.lower()
    pad = unit * 0.14
    if any(word in text for word in DATA_WORDS):
        # a flat bar chart on a card
        card = (pad, pad, width - pad, height - pad)
        d.rounded_rectangle(card, radius=unit * 0.04, fill=(255, 255, 255))
        bars = 5
        inner_w = card[2] - card[0] - 2 * pad * 0.6
        gap = inner_w / (bars * 2 - 1)
        base = card[3] - pad * 0.6
        top = card[1] + pad * 0.6
        values = sorted(rnd.uniform(0.25, 1.0) for _ in range(bars))
        for n, value in enumerate(values):
            x = card[0] + pad * 0.6 + n * gap * 2
            y = base - (base - top) * value
            d.rounded_rectangle((x, y, x + gap, base), radius=gap * 0.2, fill=accent if n == bars - 1 else mid)
        d.line((card[0] + pad * 0.5, base, card[2] - pad * 0.5, base), fill=_mix(ink, bg, 0.7), width=max(2, unit // 200))
    elif any(word in text for word in PEOPLE_WORDS):
        # a row of simple figures
        count = 3
        span = (width - 2 * pad) / count
        for n in range(count):
            cx = pad + span * (n + 0.5)
            head = span * 0.16
            cy = height * 0.42
            fill = accent if n == 1 else mid
            d.ellipse((cx - head, cy - head, cx + head, cy + head), fill=fill)
            d.rounded_rectangle((cx - head * 1.8, cy + head * 1.4, cx + head * 1.8, cy + head * 5),
                                radius=head * 1.2, fill=fill)
    else:
        # abstract composition: overlapping rounded tiles and a circle
        for n in range(3):
            w = rnd.uniform(0.25, 0.4) * width
            h = rnd.uniform(0.3, 0.5) * height
            x = pad + n * (width - 2 * pad - w) / 2
            y = rnd.uniform(pad, height - pad - h)
            d.rounded_rectangle((x, y, x + w, y + h), radius=unit * 0.04,
                                fill=[(255, 255, 255), mid, accent][n])
        r = unit * 0.09
        cx, cy = width - pad - r, pad + r
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_mix(ink, accent, 0.3))
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


class OfflineMediaProvider:
    id = "offline"
    kinds: tuple[Kind, ...] = ("image",)

    def __init__(self, colors: ThemeColors | None = None) -> None:
        self.colors = colors

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        width, height = size_of(aspect)
        return [MediaResult(data=draw(prompt, aspect, self.colors), width=width, height=height, cost_estimate=0.0,
                            meta={"placeholder": True})]

    async def test(self) -> tuple[bool, str]:
        return True, "Built in: draws flat placeholder illustrations in the deck's colours, with no network."
