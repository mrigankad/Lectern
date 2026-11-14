"""Cell references: `q3-financials.xlsx!Churn!A1:B7` (source name, sheet, A1 range)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


@dataclass(frozen=True)
class Range:
    r0: int  # 0-based, inclusive
    c0: int
    r1: int
    c1: int

    @property
    def a1(self) -> str:
        start, end = cell_name(self.r0, self.c0), cell_name(self.r1, self.c1)
        return start if start == end else f"{start}:{end}"

    @property
    def label(self) -> str:
        """"A1 to B7" as the UI says it."""
        start, end = cell_name(self.r0, self.c0), cell_name(self.r1, self.c1)
        return start if start == end else f"{start} to {end}"


@dataclass(frozen=True)
class Ref:
    source: str
    sheet: str
    range: Range

    def __str__(self) -> str:
        return f"{self.source}!{self.sheet}!{self.range.a1}"


def col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def col_index(name: str) -> int:
    value = 0
    for ch in name.upper():
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def cell_name(row: int, col: int) -> str:
    return f"{col_name(col)}{row + 1}"


def parse_range(text: str) -> Range:
    parts = text.strip().split(":")
    if len(parts) > 2 or not parts[0]:
        raise ValueError(f"\"{text}\" is not a cell range like A1:B7.")
    cells = []
    for part in parts:
        match = _CELL.match(part.strip())
        if not match:
            raise ValueError(f"\"{text}\" is not a cell range like A1:B7.")
        cells.append((int(match.group(2)) - 1, col_index(match.group(1))))
    (ra, ca), (rb, cb) = cells[0], cells[-1]
    return Range(min(ra, rb), min(ca, cb), max(ra, rb), max(ca, cb))


def parse_ref(text: str) -> Ref:
    """`name!Sheet!A1:B7`. The sheet may be quoted ('My sheet'); the file name may contain "!" only before it."""
    parts = (text or "").rsplit("!", 2)
    if len(parts) != 3 or not parts[0] or not parts[2]:
        raise ValueError(f"\"{text}\" is not a data reference like file.xlsx!Sheet!A1:B7.")
    sheet = parts[1].strip()
    if len(sheet) >= 2 and sheet[0] == sheet[-1] == "'":
        sheet = sheet[1:-1]
    return Ref(parts[0].strip(), sheet, parse_range(parts[2]))


def looks_like_ref(text: str | None) -> bool:
    try:
        parse_ref(text or "")
        return True
    except ValueError:
        return False


def read(rows: list[list[str]], rng: Range) -> list[list[str]]:
    """The cells of the range (missing cells read as empty)."""
    out = []
    for r in range(rng.r0, rng.r1 + 1):
        row = rows[r] if r < len(rows) else []
        out.append([row[c] if c < len(row) else "" for c in range(rng.c0, rng.c1 + 1)])
    return out
