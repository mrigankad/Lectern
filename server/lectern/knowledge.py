"""The product's existing knowledge, parsed from references/*.md.

The Strategist prompt, the layout registry and the offline provider all read from here,
so the markdown files stay the single place where this knowledge is edited.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import config


@dataclass(frozen=True)
class LayoutPattern:
    name: str
    purpose: str
    structure: tuple[str, ...]
    best_for: str


@dataclass(frozen=True)
class DeckType:
    name: str
    audience: str
    length: str
    tone: str
    flow: tuple[str, ...]
    guidelines: tuple[str, ...] = field(default_factory=tuple)

    @property
    def slide_range(self) -> tuple[int, int]:
        numbers = [int(n) for n in re.findall(r"\d+", self.length)]
        if len(numbers) >= 2:
            return numbers[0], numbers[1]
        return (numbers[0], numbers[0]) if numbers else (8, 12)


def _read(name: str) -> str:
    path = config.references_dir() / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _sections(markdown: str) -> list[tuple[str, str]]:
    parts = re.split(r"^## +(.+)$", markdown, flags=re.MULTILINE)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def _field(body: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}:?\*\*:?\s*(.+)", body)
    return match.group(1).strip() if match else ""


def _list_after(body: str, label: str, numbered: bool = False) -> tuple[str, ...]:
    match = re.search(rf"\*\*{re.escape(label)}:?\*\*:?\s*\n((?:.*\n?)*?)(?:\n\s*\n|\Z)", body)
    if not match:
        return ()
    pattern = r"^\s*\d+\.\s+(.+)$" if numbered else r"^\s*-\s+(.+)$"
    return tuple(m.strip() for m in re.findall(pattern, match.group(1), flags=re.MULTILINE))


@lru_cache(maxsize=1)
def layout_patterns() -> dict[str, LayoutPattern]:
    patterns: dict[str, LayoutPattern] = {}
    for name, body in _sections(_read("layout-patterns.md")):
        patterns[name] = LayoutPattern(
            name=name,
            purpose=_field(body, "Purpose"),
            structure=_list_after(body, "Structure"),
            best_for=_field(body, "Best for"),
        )
    return patterns


@lru_cache(maxsize=1)
def deck_types() -> dict[str, DeckType]:
    types: dict[str, DeckType] = {}
    for name, body in _sections(_read("deck-types.md")):
        flow = _list_after(body, "Typical Flow", numbered=True)
        if not flow:
            continue
        types[name] = DeckType(
            name=name,
            audience=_dash_field(body, "Audience"),
            length=_dash_field(body, "Length"),
            tone=_dash_field(body, "Tone"),
            flow=flow,
            guidelines=_list_after(body, "Content Guidelines"),
        )
    return types


def _dash_field(body: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}:\s*(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


@lru_cache(maxsize=1)
def reference_text() -> str:
    """All reference files joined: the shared (cacheable) system context for model providers."""
    chunks = []
    for name in ("layout-patterns.md", "deck-types.md", "visual-guidelines.md"):
        text = _read(name).strip()
        if text:
            chunks.append(text)
    return "\n\n---\n\n".join(chunks)
