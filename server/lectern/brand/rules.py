"""Plain-language brand rules: suggested from the extraction or written by the user, checked by the lint engine.

Each rule is stored as {id, text, kind, params, enabled, source}. `kind` decides the check:
colors (only palette colours), font (theme font), logo (logo on every slide), min_size (text pt floor);
anything else is a `note`, shown and passed to the agents but not checked.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from ..engine.canvas import PlaceContext
from ..engine.lint import Issue
from ..engine.place import place
from ..schema import RenderedSlide, Slide, Theme
from .extract import HEX, _rgb

KINDS = ("colors", "font", "logo", "min_size", "note")


def new_rule(text: str, source: str, kind: str | None = None, params: dict[str, Any] | None = None,
             fonts: dict[str, str] | None = None, palette: list[str] | None = None) -> dict[str, Any]:
    if kind is None:
        kind, params = classify(text, fonts or {}, palette or [])
    return {"id": f"br_{uuid.uuid4().hex[:8]}", "text": text.strip(), "kind": kind, "params": params or {},
            "enabled": True, "source": source}


def classify(text: str, fonts: dict[str, str], palette: list[str]) -> tuple[str, dict[str, Any]]:
    """Work out what a sentence asks for. Simple and predictable on purpose."""
    lower = text.lower()
    size = re.search(r"(\d{1,2}(?:\.\d)?)\s*(?:pt|point)", lower)
    if size:
        return "min_size", {"pt": float(size.group(1))}
    if "logo" in lower:
        return "logo", {}
    hexes = [f"#{h.upper()}" for h in HEX.findall(text)]
    if hexes:
        return "colors", {"palette": hexes}
    if re.search(r"\b(colou?rs?|palette)\b", lower):
        return "colors", {"palette": palette}
    if re.search(r"\b(font|typeface|set in)\b", lower):
        for name in fonts.values():
            if name.lower() in lower:
                return "font", {"font": name}
        named = re.search(r"(?:font|typeface|set in|in)\s+([A-Z][\w-]*(?:\s[A-Z][\w-]*)*)", text)
        if named:
            return "font", {"font": named.group(1)}
    return "note", {}


def suggested_rules(palette: list[dict[str, str]], fonts: dict[str, str], has_logo: bool,
                    guide_rules: list[str]) -> list[dict[str, Any]]:
    rules = []
    hexes = [p["hex"] for p in palette]
    if hexes:
        rules.append(new_rule("Use only the brand colours: " + ", ".join(hexes), "auto", "colors",
                              {"palette": hexes}))
    font = fonts.get("body") or fonts.get("heading")
    if font:
        rules.append(new_rule(f"Set all text in {font}", "auto", "font", {"font": font}))
    if has_logo:
        rules.append(new_rule("Show the logo on every slide", "auto", "logo", {}))
    rules.append(new_rule("Keep text at 10 pt or larger", "auto", "min_size", {"pt": 10.0}))
    for sentence in guide_rules:
        rules.append(new_rule(sentence, "guide", fonts=fonts, palette=hexes))
    return rules


# ---------------------------------------------------------------- checks
def _neutral(hex_: str) -> bool:
    r, g, b = _rgb(hex_)
    return max(r, g, b) - min(r, g, b) <= 18


def _close(a: str, b: str) -> bool:
    return sum(abs(x - y) for x, y in zip(_rgb(a), _rgb(b))) <= 24


def _norm(value: str | None) -> str | None:
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    return f"#{raw.upper()}" if re.fullmatch(r"[0-9A-Fa-f]{6}", raw) else None


def colors_used(rendered: RenderedSlide) -> list[str]:
    found = [rendered.background]
    for e in rendered.elements:
        if e.style:
            found += [e.style.color, e.style.fill, e.style.stroke]  # type: ignore[list-item]
        if e.chart:
            found += e.chart.colors[:max(len(e.chart.series), len(e.chart.categories) if e.chart.kind == "pie" else 0)]
    return list(dict.fromkeys(c for c in (_norm(v) for v in found) if c))


def check_rule(rule: dict[str, Any], slide: Slide, rendered: RenderedSlide, theme: Theme) -> str | None:
    """None when the slide follows the rule, else a plain sentence saying what is wrong."""
    kind, params = rule.get("kind"), rule.get("params") or {}
    if kind == "colors":
        allowed = [c for c in (_norm(v) for v in params.get("palette") or []) if c]
        if not allowed:
            return None
        theme_colors = [c for c in (_norm(v) for v in theme.colors.model_dump().values()) if c]
        off = [c for c in colors_used(rendered)
               if not _neutral(c) and not any(_close(c, a) for a in allowed + theme_colors)]
        return f"Uses colours outside the brand palette: {', '.join(off[:4])}." if off else None
    if kind == "font":
        want = str(params.get("font") or "").strip()
        if want and slide.index == 1 and theme.font.strip().lower() != want.lower():
            return f"The deck is set in {theme.font}, not {want}."
        return None
    if kind == "logo":
        if any(e.id == "brand-logo" or (e.kind == "image" and (e.alt or "").lower() == "logo")
               for e in rendered.elements):
            return None
        return "The logo is not on this slide."
    if kind == "min_size":
        floor = float(params.get("pt") or 12)
        small = [e for e in rendered.elements if e.kind in {"text", "table", "chart"} and e.style
                 and e.style.font_size and e.style.font_size * 0.5 < floor - 1e-6]
        if small:
            smallest = min(e.style.font_size for e in small if e.style and e.style.font_size) * 0.5
            return f"{len(small)} text box{'es' if len(small) > 1 else ''} below {floor:g} pt (smallest {smallest:g} pt)."
        return None
    return None


def brand_issues(rules: list[dict[str, Any]], slide: Slide, theme: Theme,
                 context: PlaceContext | None = None, rendered: RenderedSlide | None = None) -> list[Issue]:
    """Lint issues (rule `brand`) for the enabled, checkable rules of a kit. Low severity: never blocks a build."""
    rendered = rendered or place(slide, theme, context)
    issues = []
    for rule in rules:
        if not rule.get("enabled", True) or rule.get("kind") not in {"colors", "font", "logo", "min_size"}:
            continue
        problem = check_rule(rule, slide, rendered, theme)
        if problem:
            issues.append(Issue("brand", "low", f"Off brand: {rule.get('text', '')[:60]}", problem,
                                key=str(rule.get("id"))))
    return issues
