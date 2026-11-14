"""Text measurement by estimate.

There is no font engine on the server, so widths come from per-character advance classes
tuned for Urbanist. The estimate leans slightly wide so a box that fits here also fits when
PowerPoint substitutes a similar sans-serif.
"""
from __future__ import annotations

from functools import lru_cache

MIN_BODY = 24          # canvas px (= 12pt in the export)
MIN_LABEL = 20         # canvas px (= 10pt)
SAFETY = 1.04

_NARROW = set("iljI.,:;'|!`")
_SEMI_NARROW = set("ftr()[]{}\"-/\\ ")
_WIDE = set("mwMW@%&")
_WIDE_CAPS = set("ABCDEFGHKNOPQRSTUVXYZ")


def char_em(ch: str, bold: bool) -> float:
    if ch in _NARROW:
        width = 0.27
    elif ch in _SEMI_NARROW:
        width = 0.35
    elif ch in _WIDE:
        width = 0.86
    elif ch in _WIDE_CAPS:
        width = 0.67
    elif ch.isdigit() or ch in "$€£+=<>~#":
        width = 0.58
    elif ord(ch) > 0x2E80:
        width = 1.0
    else:
        width = 0.53
    return width * (1.06 if bold else 1.0)


def text_width(text: str, size: float, bold: bool = False, letter_spacing: float = 0.0,
               uppercase: bool = False) -> float:
    if uppercase:
        text = text.upper()
    return (sum(char_em(ch, bold) for ch in text) * size + letter_spacing * len(text)) * SAFETY


@lru_cache(maxsize=8192)
def wrap(text: str, size: float, width: float, bold: bool = False, letter_spacing: float = 0.0,
         uppercase: bool = False) -> tuple[str, ...]:
    """Greedy word wrap. Explicit newlines start a new line; a long word is never split."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if text_width(candidate, size, bold, letter_spacing, uppercase) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return tuple(lines)


def line_count(text: str, size: float, width: float, bold: bool = False, letter_spacing: float = 0.0,
               uppercase: bool = False) -> int:
    return len(wrap(text, size, width, bold, letter_spacing, uppercase))


def text_height(text: str, size: float, width: float, bold: bool = False, line_height: float = 1.25,
                letter_spacing: float = 0.0, uppercase: bool = False) -> float:
    return line_count(text, size, width, bold, letter_spacing, uppercase) * size * line_height


def widest_word(text: str, size: float, bold: bool = False) -> float:
    return max((text_width(word, size, bold) for word in text.split()), default=0.0)


BULLET_INDENT_EM = 1.1     # width reserved for the bullet marker, in em
BULLET_GAP_EM = 0.5        # space between bullets, in em


def bullets_height(items: list[str] | tuple[str, ...], size: float, width: float,
                   line_height: float = 1.3) -> float:
    inner = width - BULLET_INDENT_EM * size
    total = 0.0
    for item in items:
        total += text_height(item, size, inner, False, line_height)
    return total + BULLET_GAP_EM * size * max(0, len(items) - 1)


def fit_size(text: str, width: float, height: float, max_size: int, min_size: int, bold: bool = False,
             line_height: float = 1.25, max_lines: int | None = None, step: int = 2) -> int:
    """Largest size from max_size down to min_size at which the text fits the box."""
    size = max_size
    while size > min_size:
        lines = line_count(text, size, width, bold)
        if (lines * size * line_height <= height and (max_lines is None or lines <= max_lines)
                and widest_word(text, size, bold) <= width):
            return size
        size -= step
    return min_size


def fit_bullets(items: list[str], width: float, height: float, max_size: int, min_size: int,
                line_height: float = 1.3, step: int = 2) -> int:
    size = max_size
    while size > min_size:
        if bullets_height(items, size, width, line_height) <= height:
            return size
        size -= step
    return min_size
