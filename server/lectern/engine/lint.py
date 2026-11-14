"""Deterministic checks on a slide (SPEC section 6): the Critic's rule set, scores and sub-scores."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..layouts import TOPIC_HEADLINE_LAYOUTS
from ..layouts.adapt import missing_slots
from ..schema import (BulletsNode, ChartNode, Element, ItemsNode, QuoteNode, RenderedSlide, Slide, StatNode,
                      TableNode, TextNode, Theme)
from . import text as tx
from .components import table_metrics
from .canvas import Box, PlaceContext
from .numbers import Quantity, find_quantities
from .place import place
from .verbs import has_verb

PENALTY = {"high": 15, "medium": 8, "low": 3}
STORY_RULES = frozenset({"long_headline", "headline_not_claim", "missing_notes", "number_mismatch",
                         "rule_violation", "empty_slot", "placeholder_text"})
DESIGN_RULES = frozenset({"text_overflow", "min_font", "too_many_bullets", "long_bullet", "contrast",
                          "chart_too_many_series", "chart_wrong_kind"})
MAX_BULLETS = 5
MAX_BULLET_WORDS = 16
MAX_HEADLINE_WORDS = 12
MAX_SERIES = 5
MAX_PIE_SLICES = 6
MIN_LINE_POINTS = 3
MIN_CONTRAST = 4.5


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    title: str
    detail: str
    key: str = ""     # distinguishes several issues of one rule on a slide

    @property
    def fingerprint(self) -> str:
        return f"{self.rule}:{self.key}"


def words(text: str) -> int:
    return len(re.findall(r"[^\s]+", text))


# ---------------------------------------------------------------- rules on content
def check_headline(slide: Slide) -> list[Issue]:
    issues = []
    headline = slide.headline.strip()
    count = words(headline)
    if count > MAX_HEADLINE_WORDS:
        issues.append(Issue("long_headline", "medium", "Headline is too long",
                            f"The headline has {count} words. Keep it to {MAX_HEADLINE_WORDS} or fewer so it "
                            "reads in one glance."))
    if slide.layout not in TOPIC_HEADLINE_LAYOUTS and headline and not has_verb(headline):
        issues.append(Issue("headline_not_claim", "medium", "Headline names a topic, not a claim",
                            f"\"{headline}\" has no verb. Say what the audience should conclude, "
                            "for example \"Churn rose to 4.1% in Q3\"."))
    return issues


def check_bullets(slide: Slide) -> list[Issue]:
    issues = []
    for index, node in enumerate(slide.nodes):
        if not isinstance(node, BulletsNode):
            continue
        if len(node.items) > MAX_BULLETS:
            issues.append(Issue("too_many_bullets", "medium", "Too many bullets",
                                f"This list has {len(node.items)} bullets. Keep the {MAX_BULLETS} that matter "
                                "and move the rest to the notes.", key=str(index)))
        for n, item in enumerate(node.items):
            if words(item) > MAX_BULLET_WORDS:
                issues.append(Issue("long_bullet", "low", "Bullet is too long",
                                    f"Bullet {n + 1} has {words(item)} words. Aim for {MAX_BULLET_WORDS} or "
                                    f"fewer: \"{_clip(item)}\"", key=f"{index}.{n}"))
    return issues


def check_notes(slide: Slide) -> list[Issue]:
    if slide.notes.strip():
        return []
    return [Issue("missing_notes", "low", "No speaker notes",
                  "This slide has no speaker notes. Add what you will say that is not on the slide.")]


def check_charts(slide: Slide) -> list[Issue]:
    issues = []
    for index, node in enumerate(slide.nodes):
        if not isinstance(node, ChartNode):
            continue
        if len(node.series) > MAX_SERIES:
            issues.append(Issue("chart_too_many_series", "medium", "Chart has too many series",
                                f"The chart shows {len(node.series)} series. More than {MAX_SERIES} is hard to "
                                "read; keep the ones that make the point.", key=str(index)))
        if node.kind == "pie" and len(node.categories) > MAX_PIE_SLICES:
            issues.append(Issue("chart_wrong_kind", "medium", "Pie chart has too many slices",
                                f"A pie with {len(node.categories)} slices is hard to compare. "
                                "A bar chart shows this better.", key=f"{index}.pie"))
        if node.kind == "line" and len(node.categories) < MIN_LINE_POINTS:
            issues.append(Issue("chart_wrong_kind", "medium", "Line chart has too few points",
                                f"A line needs at least {MIN_LINE_POINTS} points to show a trend; this has "
                                f"{len(node.categories)}. Use bars to compare two values.", key=f"{index}.line"))
    return issues


def check_slots(slide: Slide) -> list[Issue]:
    return [Issue("empty_slot", "high", "Layout is missing content",
                  f"The {slide.layout.replace('_', ' ')} layout needs {_article(slot.type)} "
                  f"({slot.description.rstrip('.').lower() or slot.name}), and the slide has none.", key=slot.name)
            for slot in missing_slots(slide.layout, slide.nodes)]


def slide_values(slide: Slide) -> list[Quantity]:
    """The numbers the slide states as data: stat values and chart points."""
    values: list[Quantity] = []
    for node in slide.nodes:
        if isinstance(node, StatNode):
            values.extend(find_quantities(node.value))
        elif isinstance(node, ChartNode):
            unit = (node.unit or "").strip()
            for series in node.series:
                values.extend(Quantity(value=v, unit=unit, text=f"{v:g}{unit}") for v in series.values)
    return values


def slide_texts(slide: Slide, include_data: bool = False) -> list[tuple[str, str]]:
    """(where, text) for every piece of prose on the slide."""
    texts: list[tuple[str, str]] = [("headline", slide.headline)]
    for node in slide.nodes:
        if isinstance(node, TextNode) and node.role != "headline":
            texts.append((node.role, node.value))
        elif isinstance(node, BulletsNode):
            texts.extend(("bullets", item) for item in node.items)
        elif isinstance(node, QuoteNode):
            texts.append(("quote", f"{node.text} {node.attribution or ''}"))
        elif isinstance(node, ItemsNode):
            texts.extend(("items", f"{i.title} {i.body or ''} {i.label or ''}") for i in node.items)
        elif isinstance(node, StatNode):
            texts.append(("stat", f"{node.caption or ''} {node.source or ''}"))
            if include_data:
                texts.append(("stat", node.value))
        elif isinstance(node, TableNode) and include_data:
            texts.append(("table", " ".join([*node.columns, *(c for row in node.rows for c in row)])))
        elif isinstance(node, ChartNode) and include_data:
            texts.append(("chart", " ".join([node.title or "", *node.categories, *(s.name for s in node.series)])))
    texts.append(("notes", slide.notes))
    return texts


def data_like(found: Quantity) -> bool:
    """A number that reads as a data value: it has a unit ("4.1%", "$1.2M"), a decimal ("1.6") or is large
    ("1,297"). Bare small integers ("3 steps", "2 options") are counts, not data."""
    return bool(found.unit) or "." in found.text or found.value >= 1000


def comparable(found: Quantity, values: list[Any], unit_of: Any) -> list[Any]:
    """The values a number in the text should be compared with: the same unit, or, for a bare number
    ("rose from 1.2 to 1.6" under a $M chart), every value on the slide."""
    if not found.unit:
        return list(values)
    return [v for v in values if unit_of(v) == found.unit]


def check_numbers(slide: Slide) -> list[Issue]:
    """A number in the notes or text that is close to, but not the same as, one of the slide's data values.

    "Close" means the same unit and within 15%: the pattern of a figure that drifted between drafts
    (4.1% on the slide, 4.2% in the notes). Numbers that match any slide value exactly are fine.
    """
    values = slide_values(slide)
    if not values:
        return []
    issues: list[Issue] = []
    seen: set[str] = set()
    for where, text in slide_texts(slide):
        for found in find_quantities(text):
            if not data_like(found):
                continue  # bare counts such as "3 steps" are not data
            same_unit = comparable(found, values, lambda v: v.unit)
            if not same_unit or any(abs(v.value - found.value) < 1e-9 for v in same_unit):
                continue
            near = [v for v in same_unit if v.value and abs(v.value - found.value) / abs(v.value) <= 0.15]
            if not near or found.text in seen:
                continue
            seen.add(found.text)
            issues.append(Issue("number_mismatch", "high", "A number does not match the slide's data",
                                f"The {where} says {found.text}, but the slide's data shows {near[0].text}. "
                                "Make them agree.", key=found.text))
    return issues


def banned_terms(rule_text: str) -> list[str]:
    """Words or phrases a user rule bans, e.g. "Never say 'synergy'" or "Avoid the word leverage"."""
    if not re.search(r"\b(never|don'?t|do not|avoid|no|ban(?:ned)?|stop|without)\b", rule_text, re.IGNORECASE):
        return []
    quoted = re.findall(r"[\"“”'‘’]([^\"“”'‘’]{2,40})[\"“”'‘’]", rule_text)
    if quoted:
        return [q.strip() for q in quoted if q.strip()]
    match = re.search(r"\b(?:the )?(?:words?|phrases?|terms?)\s*:?\s+([\w\-]+(?:(?:\s*,\s*|\s+(?:or|and)\s+)[\w\-]+)*)",
                      rule_text, re.IGNORECASE)
    if not match:
        match = re.search(r"\b(?:say(?:ing)?|us(?:e|ing)|writ(?:e|ing))\s*:?\s+([\w\-]+)\s*[.!]?\s*$", rule_text,
                          re.IGNORECASE)
    if not match:
        match = re.search(r"^\s*(?:avoid|ban|no)\s*:?\s+([\w\-]+(?:\s*,\s*[\w\-]+)*)\s*[.!]?\s*$", rule_text,
                          re.IGNORECASE)
    if not match:
        return []
    return [t for t in re.split(r"\s*,\s*|\s+(?:or|and)\s+", match.group(1)) if t]


def check_rules(slide: Slide, rules: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    texts = slide_texts(slide, include_data=True)
    for rule_text in rules:
        for term in banned_terms(rule_text):
            pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            where = sorted({place_ for place_, text in texts if pattern.search(text)})
            if where:
                issues.append(Issue("rule_violation", "high", f"Uses \"{term}\", which your rules ban",
                                    f"\"{term}\" appears in the {', '.join(where)}. Your rule: \"{rule_text}\"",
                                    key=term.lower()))
    return issues


# ---------------------------------------------------------------- rules on the rendered slide
def needed_height(element: Element) -> float:
    style = element.style
    size = (style.font_size if style else None) or 24
    bold = bool(style and style.font_weight == 700)
    line_height = (style.line_height if style else None) or 1.25
    if element.bullets:
        return tx.bullets_height(element.bullets, size, element.w, line_height)
    spacing = (style.letter_spacing if style else None) or 0.0
    upper = bool(style and style.uppercase)
    return tx.text_height(element.text or "", size, element.w, bold, line_height, spacing, upper)


def check_overflow(slide: Slide, rendered: RenderedSlide) -> list[Issue]:
    issues: list[Issue] = []
    flagged: set[int | None] = set()
    for element in rendered.elements:
        over = False
        if element.kind == "text":
            needed = needed_height(element)
            size = (element.style.font_size if element.style else None) or 24
            bold = bool(element.style and element.style.font_weight == 700)
            too_wide = not element.bullets and tx.widest_word(element.text or "", size, bold) > element.w * 1.02
            over = needed > element.h * 1.04 + 4 or too_wide
        elif element.kind == "table" and element.table is not None:
            table = TableNode(columns=element.table.columns, rows=element.table.rows)
            _size, _row, total = table_metrics(table, Box(element.x, element.y, element.w, element.h))
            over = total > element.h * 1.04 + 4
        if over and element.node not in flagged:
            flagged.add(element.node)
            what = _describe(slide, element)
            issues.append(Issue("text_overflow", "high", "Text does not fit its box",
                                f"The {what} is too long for the space the {slide.layout.replace('_', ' ')} "
                                "layout gives it, even at the smallest allowed size. Shorten it or change "
                                "the layout.", key=str(element.node)))
    return issues


def check_fonts(slide: Slide, rendered: RenderedSlide) -> list[Issue]:
    for element in rendered.elements:
        if element.kind != "text" or not element.style or element.style.font_size is None:
            continue
        size = element.style.font_size
        body_like = bool(element.bullets) or words(element.text or "") > 8
        if size < tx.MIN_LABEL or (body_like and size < tx.MIN_BODY):
            return [Issue("min_font", "medium", "Text is too small to read",
                          f"The {_describe(slide, element)} is set at {size / 2:g}pt. Body text should be at "
                          "least 12pt and labels at least 10pt.")]
    return []


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def background_of(element: Element, rendered: RenderedSlide) -> str:
    """Fill of the topmost rect drawn before the element that covers its centre, else the slide background."""
    cx, cy = element.x + element.w / 2, element.y + element.h / 2
    fill = rendered.background
    for other in rendered.elements:
        if other is element:
            break
        if (other.kind == "rect" and other.style and other.style.fill
                and other.x <= cx <= other.x + other.w and other.y <= cy <= other.y + other.h):
            fill = other.style.fill
    return fill


def check_contrast(slide: Slide, rendered: RenderedSlide) -> list[Issue]:
    for element in rendered.elements:
        if element.kind != "text" or not element.style or not element.style.color:
            continue
        background = background_of(element, rendered)
        ratio = contrast_ratio(element.style.color, background)
        if ratio < MIN_CONTRAST:
            return [Issue("contrast", "medium", "Text is hard to read against its background",
                          f"The {_describe(slide, element)} ({element.style.color} on {background}) has a "
                          f"contrast of {ratio:.1f}:1. It needs at least {MIN_CONTRAST}:1.")]
    return []


# "[name the cause]", "$ TBD", "Use 1 (to confirm)", "XX%": text a writer left for the user to fill in.
_PLACEHOLDER = re.compile(r"\[[^\]]*[A-Za-z][^\]]*\]|\bTBD\b|\bTBC\b|\(to confirm\)|\bX{2,}\b|\blorem ipsum\b",
                          re.IGNORECASE)
# Template text written as an instruction to the presenter ("Area N: name the segment", "Add the segment, its
# share of lost logos", "Insert chart here", "Describe your solution"). "add the" only counts at the start of a
# text, followed by a template tell, so a plan bullet such as "Add the two support hires" is not flagged.
_INSTRUCTION = re.compile(
    r"(?:^|[:/–—-]\s*)(?:name the|describe (?:your|the|what|how)|insert|list (?:your|the))\b|\binsert (?:a|an|the|your)\b"
    r"|\bfill (?:this|it) in\b|\bgoes here\b|\b(?:area|item|step|segment|option|point|metric|value)\s+[NX]\b"
    r"|^\s*add (?:the|your|a|an)\b(?=.*(?:,\s*its\b|\bhere\b|\be\.g\.|\bsuch as\b))",
    re.IGNORECASE)


def _placeholder_texts(slide: Slide) -> list[tuple[str, str]]:
    """Every text on the slide face, one piece at a time (an item's title and body separately, so a
    template tell at the start of a body is seen), without the notes."""
    out: list[tuple[str, str]] = []
    for where, text in slide_texts(slide, include_data=True):
        if where in {"notes", "items"}:
            continue
        out.append((where, text))
    for node in slide.nodes:
        if isinstance(node, ItemsNode):
            for item in node.items:
                out.extend(("items", part) for part in (item.title, item.body or "", item.label or "") if part)
                out.extend(("items", line) for line in (item.body or "").splitlines()[1:] if line.strip())
    return out


def check_placeholders(slide: Slide) -> list[Issue]:
    """Placeholder text on the slide itself (the notes may say what to add)."""
    found = [(where, m.group(0) if m.re is _PLACEHOLDER else text.strip())
             for where, text in _placeholder_texts(slide)
             for m in [_PLACEHOLDER.search(text or "") or _INSTRUCTION.search(text or "")] if m]
    if not found:
        return []
    where, sample = found[0]
    more = f" and {len(found) - 1} more" if len(found) > 1 else ""
    return [Issue("placeholder_text", "high", "Slide still has placeholder text",
                  f"The {where} says \"{_clip(sample, 40)}\"{more}. Add the real content, turn the slide into "
                  "what you still need to find out, or cut it. The slide is not ready until this is fixed or kept.")]


# ---------------------------------------------------------------- entry points
def lint_slide(slide: Slide, theme: Theme | None = None, rules: list[str] | None = None,
               context: PlaceContext | None = None) -> list[Issue]:
    rendered = place(slide, theme, context)
    issues = [
        *check_headline(slide), *check_bullets(slide), *check_notes(slide), *check_charts(slide),
        *check_slots(slide), *check_placeholders(slide), *check_numbers(slide), *check_rules(slide, rules or []),
        *check_overflow(slide, rendered), *check_fonts(slide, rendered), *check_contrast(slide, rendered),
    ]
    linked = check_linked(slide)
    # A number checked against the sheet is reported once, naming the cell.
    by_sheet = {i.key.split(":", 1)[1] for i in linked if i.key.startswith("sheet:")}
    return [i for i in issues if not (i.rule == "number_mismatch" and i.key in by_sheet)] + linked


def check_linked(slide: Slide) -> list[Issue]:
    """`number_mismatch` against the cells a linked chart or stat points at (lectern/sources/link.py)."""
    if not any(getattr(n, "data_ref", None) or getattr(n, "source", None) for n in slide.nodes):
        return []
    try:
        from ..sources import link
        return link.check(slide)
    except Exception:  # noqa: BLE001  (no database or unreadable source: the pure checks still stand)
        return []


def slide_score(issues: list[Issue], rules: frozenset[str] | None = None) -> int:
    """100 minus the penalty of each issue, optionally only for one group of rules."""
    penalty = sum(PENALTY.get(i.severity, 0) for i in issues if rules is None or i.rule in rules)
    return max(0, 100 - penalty)


def mean(values: list[int]) -> int:
    return round(sum(values) / len(values)) if values else 100


def is_blocking(issue: Issue) -> bool:
    """Issues worth sending a slide back for during the build."""
    return issue.severity in {"high", "medium"}


# ---------------------------------------------------------------- helpers
def _describe(slide: Slide, element: Element) -> str:
    if element.node is None or element.node >= len(slide.nodes):
        return "label"
    node = slide.nodes[element.node]
    if isinstance(node, TextNode):
        return node.role
    return {"bullets": "bullet list", "stat": "number", "items": "item text", "quote": "quote",
            "table": "table"}.get(node.type, node.type)


def _article(node_type: str) -> str:
    return {"items": "a list of items", "bullets": "a bullet list", "stat": "a number", "chart": "a chart",
            "table": "a table", "quote": "a quote", "text": "text"}.get(node_type, node_type)


def _clip(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _luminance(color: str) -> float:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    try:
        channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return 1.0
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
