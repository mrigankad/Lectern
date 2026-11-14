"""The Analyst: reads data sources, pulls out the key numbers with exact cell or page references, and
suggests a chart for a range with a reason (chart rules from references/visual-guidelines.md).

It is deterministic code, so the numbers it hands the Strategist and Writer are exactly what the cells say,
whichever model provider writes the deck.
"""
from __future__ import annotations

import re
from typing import Any

from ..engine.numbers import find_quantities
from . import refs, service
from .parse import number_of

MAX_SERIES = 5
MAX_PIE = 5
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_TIME = re.compile(r"^(?:(?:q[1-4]|h[12]|fy)\s*'?\d{0,4}|(?:19|20)\d{2}(?:[-/]\d{1,2})*|w(?:ee)?k\s*\d+|"
                   r"(?:" + "|".join(_MONTHS) + r")[a-z]*\.?(?:\s*'?\d{2,4})?|\d{1,2}/\d{2,4}|"
                   r"(?:day|month|year|week|quarter)\s*\d+)$", re.IGNORECASE)
_SHARE = re.compile(r"\b(share|split|mix|breakdown|of total|portion)\b", re.IGNORECASE)
_BAD_UP = ("churn", "cost", "loss", "debt", "defect", "error", "incident", "spend", "expense", "attrition",
           "complaint", "latency", "downtime")


# ---------------------------------------------------------------- formatting
def fmt(value: float, unit: str) -> str:
    if unit == "$" or unit in {"€", "£", "₹"}:
        mag = abs(value)
        for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
            if mag >= div:
                return f"{'-' if value < 0 else ''}{unit}{mag / div:.3g}{suf}"
        return f"{'-' if value < 0 else ''}{unit}{mag:,.10g}"
    text = f"{value:,.2f}".rstrip("0").rstrip(".") if not float(value).is_integer() else f"{int(value):,}"
    if unit == "%":
        return text + "%"
    if unit == "pts":
        return text + " pts"
    if unit == "x":
        return text + "x"
    return text


def _unit_from_header(header: str) -> str:
    h = header.lower()
    if "%" in h or "percent" in h or "rate" in h:
        return "%"
    if "$" in h or "usd" in h:
        return "$"
    return ""


_CUR = "[$\u20ac\u00a3\u20b9]"
_HEADER_SCALE = ((re.compile(_CUR + r"\s*(?:bn|b)\b|\bbillions?\b|\(\s*b\s*\)", re.IGNORECASE), 1e9),
                 (re.compile(_CUR + r"\s*(?:mm|m)\b|\bmillions?\b|\(\s*m\s*\)", re.IGNORECASE), 1e6),
                 (re.compile(_CUR + r"\s*(?:k|000s?)\b|\bthousands?\b|\(\s*k\s*\)", re.IGNORECASE), 1e3))


def scale_from_header(header: str) -> float:
    """The multiplier a header states for its column: "Revenue ($K)" holds thousands, "ARR ($M)" millions."""
    for pattern, scale in _HEADER_SCALE:
        if pattern.search(header or ""):
            return scale
    return 1.0


def is_time(labels: list[str]) -> bool:
    labels = [x for x in labels if x]
    return len(labels) >= 2 and sum(bool(_TIME.match(x.strip())) for x in labels) >= max(2, len(labels) * 0.8)


# ---------------------------------------------------------------- a range as a table
def table_of(cells: list[list[str]]) -> dict[str, Any]:
    """Split a block of cells into categories, numeric series and units.

    The first row is a header when it holds no numbers; the first column holds category labels when
    it is not numeric. Every other column that is mostly numbers becomes a series."""
    rows = [r for r in cells if any(c.strip() for c in r)]
    if not rows:
        return {"categories": [], "series": [], "units": [], "header": False, "label_col": False}
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = all(number_of(c) is None for c in rows[0] if c.strip()) and len(rows) > 1
    body = rows[1:] if header else rows
    heads = rows[0] if header else [""] * width
    label_col = width > 1 and sum(number_of(r[0]) is None for r in body if r[0].strip()) >= max(1, len(body) // 2)
    if width == 1:
        label_col = False
    categories = [r[0] for r in body] if label_col else [str(i + 1) for i in range(len(body))]
    series, units = [], []
    for c in range(1 if label_col else 0, width):
        values = [number_of(r[c]) for r in body]
        numeric = [v for v in values if v is not None]
        if not numeric or len(numeric) < max(1, len(body) * 0.6):
            continue
        unit = next((u for _, u in numeric if u), "") or _unit_from_header(heads[c])
        name = heads[c].strip() or (f"Column {refs.col_name(c)}")
        # A bare number under "Revenue ($K)" is in thousands; scale it so it formats as $3.23M, not $3.23k.
        scale = scale_from_header(heads[c]) if not any(u for _, u in numeric) else 1.0
        if scale != 1.0:
            name = re.sub(r"\s*\([^)]*\)\s*$", "", name) or name   # the scale is now in the values
        series.append({"name": name, "values": [v[0] * scale if v else 0.0 for v in values], "col": c,
                       "scale": scale})
        units.append(unit)
    return {"categories": categories, "series": series, "units": units, "header": header, "label_col": label_col}


def _good_direction(name: str) -> str:
    return "down" if any(w in name.lower() for w in _BAD_UP) else "up"


def _headline(table: dict[str, Any], kind: str, unit: str) -> str:
    cats, series = table["categories"], table["series"]
    if not series or not cats:
        return ""
    first = series[0]
    name = re.sub(r"\s*\(?%\)?\s*$", "", first["name"]).strip() or "The value"
    vals = first["values"]
    if kind in {"line", "area"} and len(vals) >= 2:
        a, b = vals[0], vals[-1]
        verb = "rose" if b > a else "fell" if b < a else "held"
        if verb == "held":
            return f"{name} held at {fmt(b, unit)} from {cats[0]} to {cats[-1]}"
        return f"{name} {verb} from {fmt(a, unit)} to {fmt(b, unit)}"
    if kind == "pie":
        i = max(range(len(vals)), key=lambda k: vals[k])
        total = sum(vals) or 1
        return f"{cats[i]} makes up {round(vals[i] / total * 100)}% of {name.lower()}"
    i = max(range(len(vals)), key=lambda k: vals[k])
    return f"{cats[i]} leads {name.lower()} at {fmt(vals[i], unit)}"


def suggest(cells: list[list[str]]) -> dict[str, Any]:
    """A chart for the cells: kind, reason, alternatives (each with whether it suits and why)."""
    table = table_of(cells)
    cats, series = table["categories"], table["series"]
    if not series:
        return {"ok": False, "reason": "These cells have no column of numbers to chart. Pick a range with a "
                "label column and at least one column of numbers.", "table": table}
    unit = table["units"][0] if table["units"] else ""
    n, m = len(cats), len(series)
    time = is_time(cats)
    positive = all(v >= 0 for s in series for v in s["values"])
    total = sum(series[0]["values"])
    shares = m == 1 and positive and 2 <= n <= MAX_PIE and (
        (unit == "%" and 95 <= total <= 105) or bool(_SHARE.search(series[0]["name"])))
    if time and n >= 3:
        kind = "line"
        reason = (f"You picked {'one number' if m == 1 else f'{m} numbers'} per "
                  f"{_period_word(cats)}, and the point is the direction. A line shows the change over time "
                  "at a glance. The axis starts at zero so the movement is not exaggerated.")
    elif shares:
        kind = "pie"
        reason = (f"The {n} values add up to a whole, so a pie shows each part's share. It works because there "
                  f"are only {n} slices.")
    else:
        kind = "bar"
        if time:
            reason = (f"With only {n} periods, bars compare the values side by side better than a line, "
                      "which needs at least three points to show a trend.")
        else:
            reason = (f"You are comparing {n} categories{' across ' + str(m) + ' series' if m > 1 else ''}. "
                      "Bars make the differences easy to compare, and the axis starts at zero so they are honest.")
    alternatives = []
    for alt in ("bar", "line", "area", "pie", "table"):
        ok, why = _fits(alt, n, m, time, positive, shares)
        alternatives.append({"kind": alt, "ok": ok, "reason": why})
    warnings = []
    if m > MAX_SERIES:
        warnings.append(f"Only the first {MAX_SERIES} of {m} series fit on one chart.")
    return {"ok": True, "kind": kind, "reason": reason, "alternatives": alternatives,
            "categories": cats, "series": [{"name": s["name"], "values": s["values"]} for s in series[:MAX_SERIES]],
            "unit": unit or None, "headline": _headline(table, kind, unit), "warnings": warnings,
            "table": table}


def _period_word(cats: list[str]) -> str:
    first = cats[0].strip().lower() if cats else ""
    if first[:3] in _MONTHS:
        return "month"
    if first.startswith("q"):
        return "quarter"
    if re.match(r"^(19|20)\d{2}$", first):
        return "year"
    return "period"


def _fits(kind: str, n: int, m: int, time: bool, positive: bool, shares: bool) -> tuple[bool, str]:
    if kind == "line":
        return (n >= 3, "Shows change over time." if n >= 3 else "A line needs at least three points.")
    if kind == "area":
        return (n >= 3 and m <= 3, "Stresses the size of the change." if n >= 3 else
                "An area needs at least three points.")
    if kind == "pie":
        if m > 1:
            return False, "A pie shows one series only."
        if not positive or n > 6:
            return False, "A pie needs 2 to 6 positive parts of one whole."
        return shares, "Shows parts of a whole." if shares else "These values are not parts of one whole."
    if kind == "table":
        return True, "Shows the exact numbers, for detail."
    return True, "Compares values side by side."


def chart_node(cells: list[list[str]], data_ref: str, kind: str | None = None,
               title: str | None = None) -> dict[str, Any]:
    """A `chart` (or `table`) node for the cells, linked to them by data_ref."""
    s = suggest(cells)
    if not s["ok"]:
        raise ValueError(s["reason"])
    kind = kind or s["kind"]
    if kind == "table":
        table = [r for r in cells if any(c.strip() for c in r)]
        head = table[0] if s["table"]["header"] else [f"Column {refs.col_name(i)}" for i in range(len(table[0]))]
        return {"type": "table", "columns": head, "rows": table[1:] if s["table"]["header"] else table}
    node: dict[str, Any] = {"type": "chart", "kind": kind, "categories": s["categories"], "series": s["series"],
                            "data_ref": data_ref}
    if s["unit"]:
        node["unit"] = s["unit"]
    if title:
        node["title"] = title
    return node


# ---------------------------------------------------------------- facts for the deck
def _blocks(rows: list[list[str]]) -> list[refs.Range]:
    """Contiguous tables in a sheet: runs of non-empty rows, trimmed to their used columns."""
    blocks, start = [], None
    for r, row in enumerate(rows + [[]]):
        filled = any(c.strip() for c in row)
        if filled and start is None:
            start = r
        elif not filled and start is not None:
            cols = [c for rr in rows[start:r] for c, v in enumerate(rr) if v.strip()]
            blocks.append(refs.Range(start, min(cols), r - 1, max(cols)))
            start = None
    return [b for b in blocks if b.r1 - b.r0 >= 1]


def analyze(source_id: str) -> dict[str, Any]:
    """Key numbers (with refs) and chart suggestions for one source."""
    row = service.get(source_id)
    parsed = service.parsed(source_id)
    facts: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    for sheet in parsed.get("sheets") or []:
        rows = sheet["rows"]
        for block in _blocks(rows)[:3]:
            cells = refs.read(rows, block)
            table = table_of(cells)
            if not table["series"] or len(table["categories"]) < 2:
                continue
            first_data = block.r0 + (1 if table["header"] else 0)
            # Rows like "Change" or "Total" under the data are summaries, not points.
            labels = table["categories"]
            keep = len(labels)
            while keep > 2 and re.match(r"^(total|sum|change|avg|average|delta|diff)", labels[keep - 1].strip(),
                                        re.IGNORECASE):
                keep -= 1
            facts.extend(_series_facts(row.name, sheet["name"], table, block, first_data, keep, labels))
            chart = _block_chart(row, sheet, table, block, first_data, keep)
            if chart:
                charts.append(chart)
    for chunk in parsed.get("chunks") or []:
        facts.extend(_text_facts(row.name, chunk))
    return {"source_id": row.id, "name": row.name, "facts": facts, "charts": charts}


def _block_chart(row: Any, sheet: dict[str, Any], table: dict[str, Any], block: refs.Range, first_data: int,
                 keep: int) -> dict[str, Any] | None:
    """One chart per scale: the label column plus the adjacent series that share the first one's unit and
    size (churn % and revenue $ do not belong on one axis)."""
    series, units = table["series"], table["units"]
    first = series[0]
    if table["label_col"] and first["col"] != 1:
        return None
    last = first["col"]
    peak = max(abs(v) for v in first["values"]) or 1
    for nxt, unit in zip(series[1:MAX_SERIES], units[1:MAX_SERIES]):
        big = max(abs(v) for v in nxt["values"]) or 1
        if nxt["col"] != last + 1 or unit != units[0] or not 0.1 <= big / peak <= 10:
            break
        last = nxt["col"]
    chart_range = refs.Range(block.r0, block.c0, first_data + keep - 1, block.c0 + last)
    suggestion = suggest(refs.read(sheet["rows"], chart_range))
    if not suggestion["ok"]:
        return None
    return {"kind": "chart", "data_ref": str(refs.Ref(row.name, sheet["name"], chart_range)),
            "chart": suggestion["kind"], "reason": suggestion["reason"], "headline": suggestion["headline"],
            "label": f"{sheet['name']}, {chart_range.label}", "source_id": row.id}


def _series_facts(source: str, sheet: str, table: dict[str, Any], block: refs.Range, first_data: int, keep: int,
                  labels: list[str]) -> list[dict[str, Any]]:
    facts = []
    label_col = block.c0 if table["label_col"] else None
    for s, unit in zip(table["series"][:3], table["units"][:3]):
        col = block.c0 + s["col"]
        vals = s["values"][:keep]
        if not vals:
            continue
        first_ref, last_ref = refs.cell_name(first_data, col), refs.cell_name(first_data + keep - 1, col)
        name = re.sub(r"\s*\(?%\)?\s*$", "", s["name"]).strip() or s["name"]
        latest = vals[-1]
        facts.append({"kind": "number", "label": f"{name}, {labels[keep - 1]}" if label_col is not None else name,
                      "value": fmt(latest, unit), "number": latest, "unit": unit,
                      "ref": f"{source}!{sheet}!{last_ref}"})
        if len(vals) >= 2 and vals[0] != latest:
            direction = "up" if latest > vals[0] else "down"
            facts.append({"kind": "change", "label": name, "from": fmt(vals[0], unit), "value": fmt(latest, unit),
                          "number": latest, "unit": unit, "direction": direction,
                          "period": f"{labels[0]} to {labels[keep - 1]}",
                          "good": direction == _good_direction(name),
                          "ref": f"{source}!{sheet}!{first_ref}:{last_ref}"})
        if unit != "%" and len(vals) >= 2 and all(v >= 0 for v in vals):
            facts.append({"kind": "total", "label": f"Total {name.lower()}", "value": fmt(sum(vals), unit),
                          "number": sum(vals), "unit": unit, "ref": f"{source}!{sheet}!{first_ref}:{last_ref}"})
    return facts


def _text_facts(source: str, chunk: dict[str, str]) -> list[dict[str, Any]]:
    facts = []
    for sentence in re.split(r"(?<=[.!?])\s+", chunk["text"]):
        found = [q for q in find_quantities(sentence) if q.unit]
        if found and 4 <= len(sentence.split()) <= 40:
            facts.append({"kind": "quote", "label": sentence.strip()[:200], "value": found[0].text,
                          "number": found[0].value, "unit": found[0].unit, "ref": f"{source} {chunk['ref']}"})
        if len(facts) >= 4:
            break
    return facts


def facts_for(source_ids: list[str], limit: int = 16) -> list[dict[str, Any]]:
    """The Analyst's hand-off for the Strategist and Writer: charts first, then numbers."""
    charts, numbers = [], []
    for sid in source_ids:
        try:
            found = analyze(sid)
        except Exception:  # noqa: BLE001  (an unreadable source should not stop the deck)
            continue
        charts.extend(found["charts"])
        numbers.extend(found["facts"])
    return (charts[:4] + numbers)[:limit]


def fact_sentence(fact: dict[str, Any]) -> str:
    """A fact as a plain sentence, for prompts and the offline provider."""
    if fact.get("kind") == "change":
        verb = "rose" if fact.get("direction") == "up" else "fell"
        return f"{fact['label']} {verb} from {fact['from']} to {fact['value']}."
    if fact.get("kind") == "chart":
        return ""
    if fact.get("kind") == "quote":
        return fact["label"]
    return f"{fact['label']} is {fact['value']}."


# ---------------------------------------------------------------- offline provider hooks
def data_prompt(prompt: str, facts: list[dict[str, Any]]) -> str:
    """The brief with the Analyst's movements added as sentences, so the offline writer can use them."""
    extra = []
    for fact in facts:
        if fact.get("kind") == "change" and fact.get("value") not in prompt and len(extra) < 4:
            extra.append(fact_sentence(fact))
    return prompt if not extra else prompt.rstrip() + ("" if prompt.rstrip().endswith(".") else ".") + " " + \
        " ".join(extra)


def link_offline_slide(slide: Any, target: dict[str, Any], payload: dict[str, Any]) -> Any:
    """Offline Writer: a chart slide shows the Analyst's suggested chart, linked to its cells; a stat that
    repeats a number from the data cites the cell."""
    from ..schema import ChartNode, StatNode
    from . import link

    facts = (payload.get("brief") or {}).get("data_facts") or []
    charts = [f for f in facts if f.get("kind") == "chart"]
    nodes = list(slide.nodes)
    notes = slide.notes
    if charts and slide.layout in {"chart", "dashboard"}:
        index = int(target.get("index") or 0)
        earlier = [o for o in payload.get("outline") or []
                   if o.get("layout") in {"chart", "dashboard"} and int(o.get("index") or 0) < index]
        fact = charts[len(earlier) % len(charts)]
        linked = link.fill_linked([ChartNode(kind=fact["chart"], categories=[], series=[],
                                             data_ref=fact["data_ref"])])[0]
        if isinstance(linked, ChartNode) and linked.data_ref:
            at = next((i for i, n in enumerate(nodes) if isinstance(n, ChartNode)), None)
            if at is None:
                nodes.append(linked)
            else:
                nodes[at] = linked
            notes = (notes.rstrip() + f" The chart comes from {fact['label']} ({fact['data_ref']}).").strip()
    numbers = {f["value"]: f["ref"] for f in facts if f.get("kind") in {"number", "change"} and "!" in f["ref"]
               and ":" not in f["ref"].rsplit("!", 1)[-1]}
    for i, node in enumerate(nodes):
        if isinstance(node, StatNode) and node.value in numbers:
            nodes[i] = node.model_copy(update={"source": numbers[node.value]})
    return slide.model_copy(update={"nodes": nodes, "notes": notes})
