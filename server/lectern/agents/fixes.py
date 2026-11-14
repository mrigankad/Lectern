"""Deterministic fixes for lint findings that need no judgement (trim, cap, swap, replace).

`fix_issue` returns the changed slide, or None when the rule needs a rewrite by the Editor.
"""
from __future__ import annotations

import re

from ..engine import lint
from ..engine.numbers import find_quantities
from ..layouts.adapt import adapt_nodes, ensure_headline, missing_slots
from ..schema import BulletsNode, ChartNode, Item, ItemsNode, Node, QuoteNode, Slide, StatNode, TableNode, TextNode

_TRAILING = {"and", "or", "but", "the", "a", "an", "of", "to", "for", "in", "on", "with", "by", "at", "from",
             "that", "which", "while", "as", "is", "are", "our", "we"}


def shorten(text: str, max_words: int) -> str:
    """Cut text to a word budget at the nearest natural break."""
    words = text.split()
    if len(words) <= max_words:
        return text
    for pattern in (r"(?<=[.!?])\s+", r"\s*[;:—–]\s+|,\s+(?:but|and|while|so|because|which)\s+", r",\s+"):
        head = re.split(pattern, text, maxsplit=1)[0].strip()
        if 3 <= len(head.split()) <= max_words:
            return head.rstrip(",;:")
    kept = words[:max_words]
    while len(kept) > 3 and kept[-1].lower().strip(",;:") in _TRAILING:
        kept.pop()
    return " ".join(kept).rstrip(",;:—–-")


def with_headline(slide: Slide, headline: str) -> Slide:
    return slide.model_copy(update={"headline": headline, "nodes": ensure_headline(slide.nodes, headline)})


def _replace_node(slide: Slide, index: int, node: Node) -> Slide:
    nodes = list(slide.nodes)
    nodes[index] = node
    return slide.model_copy(update={"nodes": nodes})


def _map_text(slide: Slide, fn) -> Slide:  # type: ignore[no-untyped-def]
    """Apply fn to every piece of prose on the slide, including the notes."""
    nodes: list[Node] = []
    for node in slide.nodes:
        if isinstance(node, TextNode):
            nodes.append(node.model_copy(update={"value": fn(node.value)}))
        elif isinstance(node, BulletsNode):
            nodes.append(node.model_copy(update={"items": [fn(i) for i in node.items]}))
        elif isinstance(node, QuoteNode):
            nodes.append(node.model_copy(update={"text": fn(node.text),
                                                 "attribution": fn(node.attribution) if node.attribution else None}))
        elif isinstance(node, ItemsNode):
            nodes.append(node.model_copy(update={"items": [
                Item(title=fn(i.title), body=fn(i.body) if i.body else None, label=fn(i.label) if i.label else None)
                for i in node.items]}))
        elif isinstance(node, StatNode):
            nodes.append(node.model_copy(update={"caption": fn(node.caption) if node.caption else None,
                                                 "source": fn(node.source) if node.source else None}))
        elif isinstance(node, TableNode):
            nodes.append(node.model_copy(update={"columns": [fn(c) for c in node.columns],
                                                 "rows": [[fn(c) for c in row] for row in node.rows]}))
        elif isinstance(node, ChartNode):
            nodes.append(node.model_copy(update={
                "title": fn(node.title) if node.title else None, "categories": [fn(c) for c in node.categories],
                "series": [s.model_copy(update={"name": fn(s.name)}) for s in node.series]}))
        else:
            nodes.append(node)
    headline = fn(slide.headline)
    return slide.model_copy(update={"headline": headline, "nodes": ensure_headline(nodes, headline),
                                    "notes": fn(slide.notes)})


def remove_term(slide: Slide, term: str) -> Slide:
    pattern = re.compile(rf"\s*(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)

    def clean(text: str) -> str:
        out = re.sub(r"\s{2,}", " ", pattern.sub("", text)).strip()
        out = re.sub(r"\s+([,.;:])", r"\1", out)
        return out[:1].upper() + out[1:] if text[:1].isupper() and out else out

    return _map_text(slide, clean)


def replace_text(slide: Slide, old: str, new: str) -> Slide:
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    return _map_text(slide, lambda text: pattern.sub(new, text))


def tighten(slide: Slide, bullet_words: int = 10, max_bullets: int = 4, body_words: int = 24) -> Slide:
    """Make everything on the slide shorter."""
    nodes: list[Node] = []
    for node in slide.nodes:
        if isinstance(node, BulletsNode):
            nodes.append(node.model_copy(update={"items": [shorten(i, bullet_words)
                                                           for i in node.items[:max_bullets]]}))
        elif isinstance(node, TextNode) and node.role in {"body", "subhead", "caption"}:
            nodes.append(node.model_copy(update={"value": shorten(node.value, body_words)}))
        elif isinstance(node, ItemsNode):
            nodes.append(node.model_copy(update={"items": [
                Item(title=shorten(i.title, 6), body=shorten(i.body, 12) if i.body and "\n" not in i.body
                     else i.body, label=i.label) for i in node.items]}))
        elif isinstance(node, QuoteNode):
            nodes.append(node.model_copy(update={"text": shorten(node.text, 28)}))
        elif isinstance(node, StatNode):
            nodes.append(node.model_copy(update={"caption": shorten(node.caption, 8) if node.caption else None}))
        else:
            nodes.append(node)
    return with_headline(slide.model_copy(update={"nodes": nodes}), shorten(slide.headline, 12))


def fix_issue(slide: Slide, rule: str, key: str = "", user_rules: list[str] | None = None) -> Slide | None:
    if rule == "long_headline":
        return with_headline(slide, shorten(slide.headline, lint.MAX_HEADLINE_WORDS))
    if rule == "too_many_bullets":
        index = _index(key, slide, BulletsNode)
        if index is None:
            return None
        node = slide.nodes[index]
        assert isinstance(node, BulletsNode)
        extra = node.items[lint.MAX_BULLETS:]
        fixed = _replace_node(slide, index, node.model_copy(update={"items": node.items[:lint.MAX_BULLETS]}))
        notes = (slide.notes.rstrip() + "\n\nAlso mention: " + "; ".join(extra)).strip()
        return fixed.model_copy(update={"notes": notes})
    if rule == "long_bullet":
        index = _index(key.split(".")[0], slide, BulletsNode)
        if index is None:
            return None
        node = slide.nodes[index]
        assert isinstance(node, BulletsNode)
        return _replace_node(slide, index, node.model_copy(update={
            "items": [shorten(i, lint.MAX_BULLET_WORDS) for i in node.items]}))
    if rule == "chart_too_many_series":
        index = _index(key, slide, ChartNode)
        if index is None:
            return None
        node = slide.nodes[index]
        assert isinstance(node, ChartNode)
        return _replace_node(slide, index, node.model_copy(update={"series": node.series[:lint.MAX_SERIES]}))
    if rule == "chart_wrong_kind":
        index = _index(key.split(".")[0], slide, ChartNode)
        if index is None:
            return None
        return _replace_node(slide, index, slide.nodes[index].model_copy(update={"kind": "bar"}))
    if rule == "number_mismatch":
        values = lint.slide_values(slide)
        found = next((q for q in find_quantities(key) if q.unit), None)
        if not found or not values:
            return None
        near = [v for v in values if v.unit == found.unit and v.value
                and abs(v.value - found.value) / abs(v.value) <= 0.15]
        if not near:
            return None
        return replace_text(slide, key, near[0].text)
    if rule == "rule_violation":
        return remove_term(slide, key) if key else None
    if rule == "empty_slot":
        adapted = slide.model_copy(update={"nodes": adapt_nodes(slide.nodes, slide.layout)})
        return adapted if not missing_slots(adapted.layout, adapted.nodes) else None
    if rule == "text_overflow":
        return tighten(slide)
    return None  # missing_notes, headline_not_claim, min_font, contrast: need a rewrite or a layout change


def _index(key: str, slide: Slide, node_type: type) -> int | None:
    try:
        index = int(key)
    except ValueError:
        index = -1
    if 0 <= index < len(slide.nodes) and isinstance(slide.nodes[index], node_type):
        return index
    return next((i for i, n in enumerate(slide.nodes) if isinstance(n, node_type)), None)
