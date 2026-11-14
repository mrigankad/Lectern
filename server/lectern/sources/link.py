"""Charts and stats linked to cells: insert, refresh from the sheet, and check slide numbers against the cells."""
from __future__ import annotations

import re
from typing import Any

from .. import store
from ..engine.numbers import Quantity, find_quantities
from ..schema import ChartNode, Node, Slide, StatNode, TableNode
from . import analyst, refs, service
from .parse import number_of

CHART_LAYOUTS = {"chart", "dashboard"}
STAT_LAYOUTS = {"big_number", "dashboard"}


def linked_ref(node: Node) -> str | None:
    if isinstance(node, ChartNode) and node.data_ref and refs.looks_like_ref(node.data_ref):
        return node.data_ref
    if isinstance(node, StatNode) and node.source and refs.looks_like_ref(node.source):
        return node.source
    return None


def with_unit(new_text: str, old_text: str | None) -> str:
    """Keep the unit a stat was written with when the cell holds a bare number ("4.1" under "Churn %")."""
    new, old = number_of(new_text), number_of(old_text or "")
    if new and not new[1] and old and old[1]:
        unit = old[1]
        return f"{unit}{new_text.strip()}" if unit in {"$", "€", "£", "₹"} else (
            f"{new_text.strip()}{'' if unit == '%' else ' '}{unit}")
    return new_text


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def stat_from_cells(cells: list[list[str]], ref: refs.Ref) -> tuple[str, str]:
    """(display value, ref of the one cell) for a stat: the last number in the range."""
    for r in range(len(cells) - 1, -1, -1):
        for c in range(len(cells[r]) - 1, -1, -1):
            if number_of(cells[r][c]) is not None:
                cell = refs.Range(ref.range.r0 + r, ref.range.c0 + c, ref.range.r0 + r, ref.range.c0 + c)
                return cells[r][c], str(refs.Ref(ref.source, ref.sheet, cell))
    raise ValueError("Those cells have no number for a stat.")


# ---------------------------------------------------------------- checks (used by the lint)
def sheet_values(slide: Slide, deck_id: str | None = None) -> list[tuple[Quantity, str, int, str]]:
    """(quantity, as the sheet writes it, node index, ref) for every cell a linked node points at."""
    out = []
    for index, node in enumerate(slide.nodes):
        ref_text = linked_ref(node)
        if not ref_text:
            continue
        try:
            _row, ref, cells = service.read_ref(ref_text, deck_id)
        except (store.NotFound, store.Conflict):
            continue
        table = analyst.table_of(cells) if isinstance(node, ChartNode) else None
        header_units = table["units"] if table else []
        scales = {s["col"]: s.get("scale", 1.0) for s in table["series"]} if table else {}
        for row in cells:
            for col, text in enumerate(row):
                parsed = number_of(text)
                if parsed is None:
                    continue
                value, unit = parsed
                if not unit:
                    value *= scales.get(col, 1.0)
                shown = text.strip()
                if not unit and isinstance(node, ChartNode):
                    unit = (node.unit or (header_units[0] if header_units else "")).strip()
                    shown = analyst.fmt(value, unit) if unit else shown
                elif not unit and isinstance(node, StatNode):
                    unit = (number_of(node.value) or (0.0, ""))[1]
                    shown = with_unit(shown, node.value)
                out.append((Quantity(value=value, unit=unit, text=shown), shown, index, ref_text))
    return out


def check(slide: Slide, deck_id: str | None = None, already: set[str] | None = None) -> list[Any]:
    """`number_mismatch` issues against the referenced cells: a linked chart or stat that no longer matches
    its sheet, and a number in the notes or text that is close to, but not the same as, a linked cell."""
    from ..engine.lint import Issue, comparable, data_like, slide_texts

    issues: list[Any] = []
    for index, node in enumerate(slide.nodes):
        ref_text = linked_ref(node)
        if not ref_text:
            continue
        try:
            _row, ref, cells = service.read_ref(ref_text, deck_id)
        except (store.NotFound, store.Conflict) as error:
            issues.append(Issue("number_mismatch", "low", "Linked data cannot be found",
                                f"The {'chart' if isinstance(node, ChartNode) else 'stat'} is linked to "
                                f"{ref_text}, but {error}", key=f"linkmissing:{index}"))
            continue
        if isinstance(node, ChartNode):
            try:
                expected = analyst.chart_node(cells, ref_text, node.kind)
            except ValueError:
                continue
            got = [v for s in node.series for v in s.values]
            want = [v for s in expected["series"] for v in s["values"]]
            if len(got) != len(want) or not all(_close(a, b) for a, b in zip(got, want)) \
                    or list(node.categories) != list(expected["categories"]):
                issues.append(Issue("number_mismatch", "high", "The chart does not match its sheet",
                                    f"The chart is linked to {ref_text}, and the cells there have changed. "
                                    "Refresh it from the sheet.", key=f"linkchart:{index}"))
        elif isinstance(node, StatNode):
            if not _has_number(cells):
                continue
            sheet_text = stat_from_cells(cells, ref)[0]
            want_q, got_q = number_of(sheet_text), number_of(node.value)
            if want_q and (got_q is None or not _close(want_q[0], got_q[0])):
                issues.append(Issue("number_mismatch", "high", "The stat does not match its sheet",
                                    f"The stat says {node.value}, but {ref_text} says {sheet_text}. "
                                    "Refresh it from the sheet.", key=f"linkstat:{index}"))
    values = sheet_values(slide, deck_id)
    if not values:
        return issues
    seen = set(already or ())
    for where, text in slide_texts(slide):
        for found in find_quantities(text):
            if not data_like(found) or found.text in seen or _is_target(text, found.text):
                continue
            same = comparable(found, values, lambda v: v[0].unit)
            if not same or any(_close(v[0].value, found.value) for v in same):
                continue
            near = [v for v in same if v[0].value and abs(v[0].value - found.value) / abs(v[0].value) <= 0.15]
            if not near:
                continue
            seen.add(found.text)
            near.sort(key=lambda v: abs(v[0].value - found.value))
            place = "speaker notes" if where == "notes" else where
            issues.append(Issue("number_mismatch", "high", "A number does not match the sheet",
                                f"The {place} on this slide say {found.text}. The sheet says {near[0][1]} "
                                f"({near[0][3]}).", key=f"sheet:{found.text}"))
    return issues


_TARGET = re.compile(r"(?:under|below|above|over|target(?:\s+of)?|goal(?:\s+of)?|back to|at least|at most|"
                     r"[<>≤≥])\s*$", re.IGNORECASE)


def _is_target(text: str, quantity: str) -> bool:
    """"Churn back under 3% by Q2" states a goal, not a reading of the sheet's 3.1%."""
    at = text.find(quantity)
    return at > 0 and bool(_TARGET.search(text[max(0, at - 24):at]))


def _has_number(cells: list[list[str]]) -> bool:
    return any(number_of(c) is not None for row in cells for c in row)


def mismatches(slide: Slide, deck_id: str | None = None) -> list[dict[str, Any]]:
    """The checks above as plain dicts for the data screen."""
    from ..engine.lint import check_numbers

    linked = check(slide, deck_id)
    by_sheet = {i.key.split(":", 1)[1] for i in linked if i.key.startswith("sheet:")}
    issues = linked + [i for i in check_numbers(slide) if i.key not in by_sheet]
    return [{"rule": i.rule, "severity": i.severity, "title": i.title, "detail": i.detail, "key": i.key}
            for i in issues]


# ---------------------------------------------------------------- changes to a slide
def _load(deck_id: str, slide_id: str) -> Slide:
    row = store.get_slide_row(deck_id, slide_id)
    if not store.editable(row):
        raise store.Conflict("This slide is being worked on by an agent. Try again in a moment.")
    return store.to_slide(row)


def _save(deck_id: str, slide: Slide, reason: str) -> Slide:
    from ..agents import apply

    apply.save(deck_id, apply.patched(slide), reason)
    store.publish_deck(deck_id)
    return store.to_slide(store.get_slide_row(deck_id, slide.id))


def insert(deck_id: str, slide_id: str, data_ref: str, as_: str = "chart", kind: str | None = None,
           title: str | None = None, headline: str | None = None) -> Slide:
    slide = _load(deck_id, slide_id)
    _row, ref, cells = service.read_ref(data_ref, deck_id)
    nodes = list(slide.nodes)
    layout = slide.layout
    if as_ == "stat":
        value, cell_ref = stat_from_cells(cells, ref)
        table = analyst.table_of(cells)
        caption = title or (table["series"][0]["name"] if table["series"] else None)
        new: Node = StatNode(value=value, caption=caption, source=cell_ref)
        at = next((i for i, n in enumerate(nodes) if isinstance(n, StatNode)), None)
        if layout not in STAT_LAYOUTS:
            layout = "big_number"
    else:
        try:
            data = analyst.chart_node(cells, str(ref), kind, title)
        except ValueError as error:
            raise store.Conflict(str(error)) from error
        new = TableNode.model_validate(data) if data["type"] == "table" else ChartNode.model_validate(data)
        at = next((i for i, n in enumerate(nodes) if isinstance(n, (ChartNode, TableNode))), None)
        if isinstance(new, TableNode) and layout != "table":
            layout = "table"
        elif isinstance(new, ChartNode) and layout not in CHART_LAYOUTS:
            layout = "chart"
    if at is None:
        nodes.append(new)
    else:
        nodes[at] = new
    update: dict[str, Any] = {"nodes": nodes, "layout": layout}
    if headline and headline.strip():
        update["headline"] = headline.strip()
        nodes[:] = [n.model_copy(update={"value": headline.strip()})
                    if getattr(n, "type", "") == "text" and getattr(n, "role", "") == "headline" else n
                    for n in nodes]
    return _save(deck_id, slide.model_copy(update=update), f"Inserted data from {data_ref}")


def refresh(deck_id: str, slide_id: str, reread: bool = True, update_text: bool = True
            ) -> tuple[Slide, list[str], dict[str, str], list[str]]:
    """Re-read every source the slide links to and bring its charts and stats in line with the cells.

    Returns (slide, changed refs, text replacements, flagged figures). Figures in the prose that were
    written from a value that changed are rewritten too (see `text_updates`); with `update_text` off the
    replacements are only offered."""
    slide = _load(deck_id, slide_id)
    linked = [(i, linked_ref(n)) for i, n in enumerate(slide.nodes) if linked_ref(n)]
    if not linked:
        raise store.Conflict("Nothing on this slide is linked to a sheet.")
    if reread:
        done: set[str] = set()
        for _i, ref_text in linked:
            row, _ref, _cells = service.read_ref(ref_text or "", deck_id)
            if row.id not in done:
                service.reload(row.id)
                done.add(row.id)
    nodes = list(slide.nodes)
    changed: list[str] = []
    for i, ref_text in linked:
        _row, ref, cells = service.read_ref(ref_text or "", deck_id)
        node = nodes[i]
        if isinstance(node, ChartNode):
            data = analyst.chart_node(cells, ref_text or "", node.kind, node.title)
            new = node.model_copy(update={"categories": data["categories"], "series": ChartNode.model_validate(
                data).series, "unit": data.get("unit", node.unit)})
        else:
            value, _cell = stat_from_cells(cells, ref)
            new = node.model_copy(update={"value": with_unit(value, node.value)})
        if new != node:
            changed.append(ref_text or "")
        nodes[i] = new
    if not changed:
        return slide, changed, {}, []
    updated = slide.model_copy(update={"nodes": nodes})
    replacements, flagged = text_updates(updated, list(slide.nodes), nodes)
    if update_text:
        updated = rewrite(updated, replacements)
    return _save(deck_id, updated, "Refreshed from sheet"), changed, replacements, flagged


def fix_numbers(deck_id: str, slide_id: str) -> tuple[Slide, int]:
    """Write the sheet's figure wherever the notes or text drifted from a linked cell."""
    slide = _load(deck_id, slide_id)
    values = sheet_values(slide, deck_id)
    replacements: dict[str, str] = {}
    from ..engine.lint import comparable, data_like, slide_texts

    for _where, text in slide_texts(slide):
        for found in find_quantities(text):
            if not data_like(found) or _is_target(text, found.text):
                continue
            same = comparable(found, values, lambda v: v[0].unit)
            if not same or any(_close(v[0].value, found.value) for v in same):
                continue
            near = sorted((v for v in same if v[0].value and abs(v[0].value - found.value) / abs(v[0].value)
                           <= 0.15), key=lambda v: abs(v[0].value - found.value))
            if near:
                replacements[found.text] = near[0][1] if found.unit else renumber(found, near[0][0].value)
    if not replacements:
        return slide, 0

    return _save(deck_id, rewrite(slide, replacements), "Matched numbers to the sheet"), len(replacements)


_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def renumber(found: Quantity, new_value: float, factor: float | None = None) -> str:
    """`found` as written, with its number replaced by `new_value` in the same style: "1.6" -> "1.7",
    "$1.6M" -> "$1.7M", "1,204" -> "1,262". `factor` is how much the written number is scaled by (M = 1e6)."""
    match = _NUM.search(found.text)
    if not match:
        return found.text
    raw = match.group(0)
    raw_value = float(raw.replace(",", ""))
    if factor is None:
        factor = found.value / raw_value if raw_value else 1.0
    shown = new_value / (factor or 1.0)
    decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
    text = f"{shown:,.{decimals}f}" if "," in raw else f"{shown:.{decimals}f}"
    if not _close(float(text.replace(",", "")), round(shown, 6)):
        text = f"{shown:,g}" if "," in raw else f"{shown:g}"
    return found.text[:match.start()] + text + found.text[match.end():]


def rewrite(slide: Slide, replacements: dict[str, str]) -> Slide:
    """The slide with each old figure in its prose (headline, text, bullets, items, captions, notes) replaced."""
    if not replacements:
        return slide
    pattern = re.compile("|".join(r"(?<![\w.,])" + re.escape(k) + r"(?![\w]|[.,]\d)"
                                  for k in sorted(replacements, key=len, reverse=True)))

    def fix(text: str | None) -> str:
        return pattern.sub(lambda m: replacements[m.group(0)], text or "")

    nodes = []
    for node in slide.nodes:
        data = node.model_dump()
        if data["type"] == "text":
            data["value"] = fix(data["value"])
        elif data["type"] == "bullets":
            data["items"] = [fix(x) for x in data["items"]]
        elif data["type"] == "items":
            for item in data["items"]:
                item["title"] = fix(item["title"])
                if item.get("body"):
                    item["body"] = fix(item["body"])
        elif data["type"] == "stat" and data.get("caption"):
            data["caption"] = fix(data["caption"])
        nodes.append(type(node).model_validate(data))
    return slide.model_copy(update={"nodes": nodes, "notes": fix(slide.notes), "headline": fix(slide.headline)})


def _points(node: Node) -> list[float]:
    if isinstance(node, ChartNode):
        return [v for s in node.series for v in s.values]
    parsed = number_of(node.value) if isinstance(node, StatNode) else None
    return [parsed[0]] if parsed else []


def text_updates(slide: Slide, before: list[Node], after: list[Node]) -> tuple[dict[str, str], list[str]]:
    """How the prose should change after a refresh: ({old text: new text}, [figures to check by hand]).

    A figure in the prose is updated when it equals a linked value that changed (a chart point or stat
    that read 1.6 and now reads 1.7): it was written from those cells. A figure equal to an old value
    that moved to several different new values, or that still equals a current value, is ambiguous: it
    is flagged, not rewritten. Everything else is left alone."""
    from ..engine.lint import data_like, slide_texts

    moves: dict[float, set[float]] = {}
    for old_node, new_node in zip(before, after):
        if isinstance(old_node, ChartNode) and isinstance(new_node, ChartNode) \
                and list(old_node.categories) != list(new_node.categories):
            continue  # the rows moved: position no longer tells which value a figure came from
        for a, b in zip(_points(old_node), _points(new_node)):
            if not _close(a, b):
                moves.setdefault(round(a, 9), set()).add(round(b, 9))
    if not moves:
        return {}, []
    current = [v for n in after for v in _points(n)]
    replacements: dict[str, str] = {}
    flagged: list[str] = []
    for _where, text in slide_texts(slide):
        for found in find_quantities(text):
            if not data_like(found) or found.text in replacements or _is_target(text, found.text):
                continue
            match = _NUM.search(found.text)
            raw_value = float(match.group(0).replace(",", "")) if match else found.value
            for value, factor in ((found.value, None), (raw_value, 1.0)):
                key = next((k for k in moves if _close(k, value)), None)
                if key is None:
                    continue
                targets = moves[key]
                if len(targets) == 1 and not any(_close(value, c) for c in current):
                    replacements[found.text] = renumber(found, next(iter(targets)), factor)
                elif found.text not in flagged:
                    flagged.append(found.text)
                break
    return replacements, flagged


def fill_linked(nodes: list[Node], deck_id: str | None = None) -> list[Node]:
    """Charts and stats an agent wrote with a data_ref get their values from the cells, so a model never
    has to copy numbers. A ref that cannot be read is dropped rather than left pointing nowhere."""
    out: list[Node] = []
    for node in nodes:
        ref_text = linked_ref(node)
        if not ref_text:
            if isinstance(node, ChartNode) and node.data_ref:
                node = node.model_copy(update={"data_ref": None})
            out.append(node)
            continue
        try:
            _row, ref, cells = service.read_ref(ref_text, deck_id)
            if isinstance(node, ChartNode):
                data = analyst.chart_node(cells, ref_text, node.kind, node.title)
                node = ChartNode.model_validate(data)
            elif isinstance(node, StatNode):
                value, cell_ref = stat_from_cells(cells, ref)
                written, cell = number_of(node.value), number_of(value)
                if written and cell and not _close(written[0], cell[0]):
                    # A derived figure ("+34%" growth linked to the latest revenue cell) is not that cell's
                    # value: keep what the agent wrote and drop the link instead of printing "3230%".
                    node = node.model_copy(update={"source": None})
                else:
                    node = node.model_copy(update={"value": with_unit(value, node.value), "source": cell_ref})
        except (store.NotFound, store.Conflict, ValueError):
            if isinstance(node, ChartNode):
                node = node.model_copy(update={"data_ref": None})
        out.append(node)
    return out
