"""Offline Editor: apply simple, clearly worded change requests to a slide without a model."""
from __future__ import annotations

import re
from typing import Any

from ...agents import fixes
from ...engine.verbs import has_verb
from ...layouts import LAYOUT_IDS
from ...layouts.adapt import adapt_nodes, ensure_headline, missing_slots
from ...schema import BulletsNode, Item, ItemsNode, Slide, TextNode
from . import writer
from .facts import Facts
from .outline import Step, headline_for

HELP = ("I can't work that change out without a model. In offline mode I understand requests like "
        "\"make it shorter\", \"change the headline to …\", \"replace X with Y\", \"add a bullet: …\", "
        "\"remove the last bullet\" or \"use the chart layout\". Connect a model in Connections for free-form edits.")

_LAYOUT_WORDS = {"two column": "two_column", "two-column": "two_column", "2 column": "two_column",
                 "three column": "three_column", "three-column": "three_column", "3 column": "three_column",
                 "big idea": "big_idea", "big number": "big_number", "next steps": "next_steps",
                 "case study": "case_study", "steps": "process", "columns": "three_column",
                 "metrics": "dashboard", "comparison": "table", "takeaways": "summary", "statement": "big_idea"}
_QUOTED = r"[\"“”'‘’]([^\"“”]+?)[\"“”'‘’]"


def _unquote(text: str) -> str:
    return text.strip().strip("\"“”'‘’ ").rstrip(".")


def _find_layout(message: str) -> str | None:
    lower = message.lower()
    for words, layout in _LAYOUT_WORDS.items():
        if words in lower:
            return layout
    for layout in LAYOUT_IDS:
        if re.search(rf"\b{layout.replace('_', '[ _-]')}s?\b", lower):
            return layout
    return None


def edit_slide(slide: Slide, message: str, facts: Facts) -> tuple[Slide | None, str]:
    """Return (changed slide or None, one-sentence summary)."""
    text = message.strip()
    lower = text.lower()

    match = re.search(rf"(?:replace|change|swap)\s+{_QUOTED}\s+(?:with|to|for)\s+{_QUOTED}", text, re.IGNORECASE) \
        or re.search(r"(?:replace|swap)\s+(.+?)\s+with\s+(.+)$", text, re.IGNORECASE)
    if match:
        old, new = _unquote(match.group(1)), _unquote(match.group(2))
        changed = fixes.replace_text(slide, old, new)
        if changed == slide:
            return None, f"I couldn't find \"{old}\" on this slide."
        return changed, f"Replaced \"{old}\" with \"{new}\"."

    match = re.search(r"(?:headline|title)\s*(?:to|:|as|should (?:be|say|read))\s*(.+)$", text, re.IGNORECASE)
    if match and len(_unquote(match.group(1))) > 2:
        headline = _unquote(match.group(1))
        return fixes.with_headline(slide, headline), f"Changed the headline to \"{headline}\"."

    match = re.search(r"add (?:a |another |one more )?(?:bullet|point|line|item)\s*(?::|about|saying|that says|"
                      r"for|on)?\s*(.+)$", text, re.IGNORECASE)
    if match and _unquote(match.group(1)):
        addition = _unquote(match.group(1))
        addition = addition[:1].upper() + addition[1:]
        nodes = list(slide.nodes)
        for index, node in enumerate(nodes):
            if isinstance(node, BulletsNode):
                nodes[index] = node.model_copy(update={"items": [*node.items, addition]})
                return slide.model_copy(update={"nodes": nodes}), f"Added the bullet \"{addition}\"."
            if isinstance(node, ItemsNode):
                nodes[index] = node.model_copy(update={"items": [*node.items, Item(title=addition)]})
                return slide.model_copy(update={"nodes": nodes}), f"Added the item \"{addition}\"."
        nodes.append(BulletsNode(items=[addition]))
        return slide.model_copy(update={"nodes": nodes}), f"Added the bullet \"{addition}\"."

    match = re.search(r"(?:remove|delete|drop|cut)\s+(?:the\s+)?(last|first|\d+(?:st|nd|rd|th)?|second|third|fourth)"
                      r"\s+(?:bullet|point|item|step|column)", lower)
    if match:
        which = match.group(1)
        position = {"first": 0, "second": 1, "third": 2, "fourth": 3, "last": -1}.get(which)
        if position is None:
            position = int(re.sub(r"\D", "", which)) - 1
        nodes = list(slide.nodes)
        for index, node in enumerate(nodes):
            if isinstance(node, (BulletsNode, ItemsNode)) and node.items:
                items = list(node.items)
                if -len(items) <= position < len(items):
                    removed = items.pop(position)
                    nodes[index] = node.model_copy(update={"items": items})
                    label = removed if isinstance(removed, str) else removed.title
                    return slide.model_copy(update={"nodes": nodes}), f"Removed \"{label}\"."
        return None, "This slide has no list to remove from."

    if re.search(r"\b(layout|turn (?:this|it) into|make (?:this|it) (?:a|an)|convert|switch to|use (?:a|an|the))\b",
                 lower):
        layout = _find_layout(lower)
        if layout and layout != slide.layout:
            changed = slide.model_copy(update={"layout": layout, "nodes": adapt_nodes(slide.nodes, layout)})
            if missing_slots(layout, changed.nodes):
                extra = writer.write_nodes({"headline": slide.headline, "layout": layout}, facts, [])
                have = {n.type for n in changed.nodes}
                merged = [*changed.nodes, *(n for n in extra if n.type not in have)]
                changed = changed.model_copy(update={"nodes": merged})
            if missing_slots(layout, changed.nodes):
                return None, (f"The {layout.replace('_', ' ')} layout needs content this slide does not have. "
                              "Add it first, or pick another layout.")
            return changed, f"Switched the slide to the {layout.replace('_', ' ')} layout."
        if layout == slide.layout:
            return None, f"This slide already uses the {layout.replace('_', ' ')} layout."

    match = re.search(r"(?:speaker )?notes?\s*(?:to|:|should say)\s*(.+)$", text, re.IGNORECASE)
    if match and "short" not in lower:
        notes = _unquote(match.group(1))
        return slide.model_copy(update={"notes": notes}), "Updated the speaker notes."

    if re.search(r"\b(shorter|shorten|tighten|tighter|concise|trim|cut down|less text|simplif|punchier|brief)", lower):
        changed = fixes.tighten(slide)
        if changed == slide:
            return None, "This slide is already as short as I can make it without changing what it says."
        return changed, "Tightened the text: shorter bullets and fewer words."

    match = re.search(rf"(?:remove|delete|don'?t (?:use|say)|avoid|drop)\s+(?:the (?:word|phrase)\s+)?{_QUOTED}",
                      text, re.IGNORECASE)
    if match:
        term = _unquote(match.group(1))
        changed = fixes.remove_term(slide, term)
        if changed == slide:
            return None, f"\"{term}\" does not appear on this slide."
        return changed, f"Removed \"{term}\"."

    return None, HELP


def claim_headline(slide: Slide, facts: Facts) -> str:
    """Rewrite a topic-style headline as a claim."""
    kind = writer.kind_of({"headline": slide.headline, "layout": slide.layout, "intent": slide.intent})
    candidate = headline_for(Step(kind=kind, name=slide.headline), facts)
    if has_verb(candidate) and candidate.lower() != slide.headline.lower():
        return candidate
    topic = slide.headline.rstrip(".")
    lowered = topic if (len(topic) > 1 and topic[1].isupper()) else topic[:1].lower() + topic[1:]
    return f"What {lowered} means for {facts.audience if facts.audience != 'the audience' else 'us'}"


def fix_finding(slide: Slide, finding: dict[str, Any], facts: Facts, user_rules: list[str]) -> tuple[Slide | None, str]:
    rule = str(finding.get("rule") or "")
    key = str(finding.get("key") or "")
    fixed = fixes.fix_issue(slide, rule, key, user_rules)
    if fixed is not None and fixed != slide:
        return fixed, f"Fixed: {str(finding.get('title') or rule).lower()}."
    payload = {"headline": slide.headline, "layout": slide.layout, "intent": slide.intent}
    if rule == "missing_notes":
        return slide.model_copy(update={"notes": writer.write_notes(payload, facts)}), "Added speaker notes."
    if rule == "headline_not_claim":
        headline = claim_headline(slide, facts)
        return fixes.with_headline(slide, headline), f"Rewrote the headline as a claim: \"{headline}\"."
    if rule == "empty_slot":
        extra = writer.write_nodes(payload, facts, [])
        have = {n.type for n in slide.nodes if not isinstance(n, TextNode)}
        merged = ensure_headline([*slide.nodes, *(n for n in extra if n.type not in have)], slide.headline)
        changed = slide.model_copy(update={"nodes": merged})
        if not missing_slots(changed.layout, changed.nodes):
            return changed, "Filled the empty part of the layout."
    return None, "This one needs your judgement: I could not fix it automatically."
