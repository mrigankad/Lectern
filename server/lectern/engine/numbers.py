"""Find quantities (a number with its unit) in text."""
from __future__ import annotations

import re
from dataclasses import dataclass

_SCALE = {"k": 1e3, "m": 1e6, "mm": 1e6, "b": 1e9, "bn": 1e9, "t": 1e12,
          "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}

_QUANTITY = re.compile(
    r"(?<![\w.])(?P<cur>[$€£₹])?\s?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<scale>thousand|million|billion|trillion|bn|mm|[kKmMbBtT])(?![A-Za-z]))?"
    r"\s?(?P<suffix>%|pp\b|bps\b|x\b|×)?",
)


@dataclass(frozen=True)
class Quantity:
    value: float     # scaled: "$1.2M" -> 1_200_000
    unit: str        # "%", "$", "x", "pp", "" ...
    text: str        # as written


def find_quantities(text: str) -> list[Quantity]:
    """Quantities in the text. Bare years and list ordinals like "Q3" are not quantities."""
    found: list[Quantity] = []
    for match in _QUANTITY.finditer(text or ""):
        raw = match.group("num")
        start = match.start("num")
        if start > 0 and text[start - 1].isalpha():
            continue  # Q3, H1, v2
        value = float(raw.replace(",", ""))
        scale = (match.group("scale") or "").lower()
        currency = match.group("cur") or ""
        suffix = (match.group("suffix") or "").lower().replace("×", "x")
        if not currency and not suffix and not scale and re.fullmatch(r"(19|20)\d{2}", raw):
            continue  # a year
        value *= _SCALE.get(scale, 1.0)
        unit = currency or suffix
        found.append(Quantity(value=value, unit=unit, text=match.group(0).strip()))
    return found
