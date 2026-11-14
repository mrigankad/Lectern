"""Data sources: store uploads and fetched links under data/sources/<id>/, parse them, look them up by ref."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable

from sqlmodel import select

from .. import config, store
from ..db import session
from ..models import SourceRow, now
from . import parse as parser
from . import refs

MAX_BYTES = 25 * 1024 * 1024
MAX_FETCH_BYTES = 8 * 1024 * 1024
_GSHEET = re.compile(r"docs\.google\.com/spreadsheets/d/(?:e/)?([A-Za-z0-9_-]+)")


def sources_dir() -> Path:
    path = config.data_dir() / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def folder(source_id: str) -> Path:
    path = sources_dir() / source_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- network (tests replace `fetcher`)
def _http_get(url: str) -> tuple[bytes, str]:
    import httpx

    try:
        with httpx.Client(follow_redirects=True, timeout=20.0,
                          headers={"User-Agent": "Lectern/0.1 (data source fetch)"}) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        raise parser.ParseError(f"Lectern could not reach that link ({error.__class__.__name__}).") from error
    if response.status_code >= 400:
        raise parser.ParseError(f"That link answered with an error (HTTP {response.status_code}).")
    if len(response.content) > MAX_FETCH_BYTES:
        raise parser.ParseError("That page is too large to read (over 8 MB).")
    return response.content, response.headers.get("content-type", "")


fetcher: Callable[[str], tuple[bytes, str]] = _http_get


def gsheet_export_url(url: str) -> str | None:
    """The public CSV export link for a Google Sheets URL, keeping the tab (gid) if the link names one."""
    match = _GSHEET.search(url)
    if not match:
        return None
    gid = re.search(r"[#&?]gid=(\d+)", url)
    if "/d/e/" in url:  # "Publish to the web" links
        return f"https://docs.google.com/spreadsheets/d/e/{match.group(1)}/pub?output=csv" + (
            f"&gid={gid.group(1)}" if gid else "")
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv" + (
        f"&gid={gid.group(1)}" if gid else "")


# ---------------------------------------------------------------- rows
def _summary(kind: str, parsed: dict[str, Any]) -> dict[str, Any]:
    sheets = parsed.get("sheets") or []
    return {
        "sheets": [{"name": s["name"], "rows": len(s["rows"]), "cols": len(s["rows"][0]) if s["rows"] else 0}
                   for s in sheets],
        "chunks": len(parsed.get("chunks") or []),
        "pages": parsed.get("pages"),
        "title": parsed.get("title"),
    }


def to_out(row: SourceRow) -> dict[str, Any]:
    return {"id": row.id, "deck_id": row.deck_id, "name": row.name, "kind": row.kind, "url": row.url,
            "bytes": row.bytes, "status": row.status, "error": row.error, "summary": row.summary,
            "created_at": row.created_at, "updated_at": row.updated_at}


def _unique_name(name: str, deck_id: str | None, exclude: str | None = None) -> str:
    name = re.sub(r"[!\\/:*?\"<>|]", "-", name).strip() or "source"
    with session() as s:
        taken = {r.name for r in s.exec(select(SourceRow).where(SourceRow.deck_id == deck_id)).all()
                 if r.id != exclude}
    if name not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, "." + ext) if dot else (name, "")
    n = 2
    while f"{stem} ({n}){ext}" in taken:
        n += 1
    return f"{stem} ({n}){ext}"


def _write(row: SourceRow, data: bytes) -> SourceRow:
    """Parse the bytes, store the original and the parsed form, and save the row."""
    parsed = parser.parse(row.kind, data, row.name)
    path = folder(row.id)
    (path / "original").write_bytes(data)
    (path / "parsed.json").write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    row.bytes = len(data)
    row.summary = _summary(row.kind, parsed)
    row.status, row.error, row.updated_at = "ready", None, now()
    with session() as s:
        s.add(row)
        s.commit()
    return row


def upload(data: bytes, filename: str, deck_id: str | None = None) -> SourceRow:
    if not data:
        raise store.Conflict("The file is empty.")
    if len(data) > MAX_BYTES:
        raise store.Conflict("The file is larger than 25 MB.")
    kind = parser.kind_for(filename or "")
    if kind is None:
        raise store.Conflict("Lectern reads XLSX, CSV, PDF, DOCX, TXT and Markdown files.")
    if deck_id:
        store.get_deck_row(deck_id)
    row = SourceRow(deck_id=deck_id, name=_unique_name(filename, deck_id), kind=kind)
    try:
        return _write(row, data)
    except parser.ParseError as error:
        shutil.rmtree(sources_dir() / row.id, ignore_errors=True)
        raise store.Conflict(str(error)) from error


def add_link(url: str, deck_id: str | None = None, name: str | None = None) -> SourceRow:
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise store.Conflict("Paste a full link that starts with http:// or https://.")
    if deck_id:
        store.get_deck_row(deck_id)
    export = gsheet_export_url(url)
    if export:
        default = f"google-sheet-{_GSHEET.search(url).group(1)[:6]}.csv"  # type: ignore[union-attr]
        row = SourceRow(deck_id=deck_id, kind="gsheet", url=url, name=_unique_name(name or default, deck_id))
    else:
        host = re.sub(r"^https?://(www\.)?", "", url, flags=re.IGNORECASE).split("/")[0]
        row = SourceRow(deck_id=deck_id, kind="url", url=url, name=_unique_name(name or host, deck_id))
    try:
        return _write(row, _fetch(row))
    except parser.ParseError as error:
        raise store.Conflict(str(error)) from error


def _fetch(row: SourceRow) -> bytes:
    if row.kind == "gsheet":
        data, ctype = fetcher(gsheet_export_url(row.url or "") or "")
        if "html" in ctype.lower() or data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
            raise parser.ParseError("That Google Sheet is not public. In Google Sheets choose Share, set "
                                    "\"Anyone with the link\" can view, and paste the link again.")
        return data
    data, ctype = fetcher(row.url or "")
    if ctype and not any(t in ctype.lower() for t in ("html", "text", "xml")):
        raise parser.ParseError("That link is not a web page. Download the file and attach it instead.")
    return data


def get(source_id: str) -> SourceRow:
    with session() as s:
        row = s.get(SourceRow, source_id)
    if row is None:
        raise store.NotFound("That data source does not exist.")
    return row


def list_sources(deck_id: str | None = None) -> list[SourceRow]:
    with session() as s:
        query = select(SourceRow)
        if deck_id:
            query = query.where(SourceRow.deck_id == deck_id)
        rows = list(s.exec(query).all())
    return sorted(rows, key=lambda r: r.created_at, reverse=True)


def attach(source_ids: list[str], deck_id: str) -> None:
    """Give sources uploaded before the deck existed to the deck."""
    with session() as s:
        for sid in source_ids:
            row = s.get(SourceRow, sid)
            if row is not None and row.deck_id in (None, deck_id):
                row.deck_id = deck_id
                s.add(row)
        s.commit()


def delete(source_id: str) -> None:
    with session() as s:
        row = s.get(SourceRow, source_id)
        if row is None:
            raise store.NotFound("That data source does not exist.")
        s.delete(row)
        s.commit()
    shutil.rmtree(sources_dir() / source_id, ignore_errors=True)


def replace_file(source_id: str, data: bytes) -> SourceRow:
    row = get(source_id)
    if row.kind in {"url", "gsheet"}:
        raise store.Conflict("This source is a link. Refresh it instead.")
    try:
        return _write(row, data)
    except parser.ParseError as error:
        raise store.Conflict(str(error)) from error


def reload(source_id: str) -> SourceRow:
    """Read the source again: fetch a link anew, re-parse a stored file."""
    row = get(source_id)
    try:
        data = _fetch(row) if row.kind in {"url", "gsheet"} else (folder(row.id) / "original").read_bytes()
        return _write(row, data)
    except (parser.ParseError, OSError) as error:
        raise store.Conflict(str(error)) from error


def parsed(source_id: str) -> dict[str, Any]:
    try:
        return json.loads((folder(source_id) / "parsed.json").read_text(encoding="utf-8"))
    except OSError as error:
        raise store.NotFound("This data source has no readable content.") from error


def original_path(source_id: str) -> Path:
    return folder(source_id) / "original"


def find_by_name(name: str, deck_id: str | None = None) -> SourceRow | None:
    with session() as s:
        rows = list(s.exec(select(SourceRow).where(SourceRow.name == name)).all())
    if not rows:
        return None
    own = [r for r in rows if r.deck_id == deck_id]
    return max(own or rows, key=lambda r: r.updated_at)


def sheet(source_id: str, name: str | None) -> dict[str, Any]:
    sheets = parsed(source_id).get("sheets") or []
    if not sheets:
        raise store.Conflict("This source has no sheets or tables.")
    if name is None:
        return sheets[0]
    found = next((s for s in sheets if s["name"] == name), None)
    if found is None:
        raise store.NotFound(f"There is no sheet called \"{name}\" in this source.")
    return found


def read_ref(ref_text: str, deck_id: str | None = None) -> tuple[SourceRow, refs.Ref, list[list[str]]]:
    """Resolve a data_ref to its source and the cells it names."""
    try:
        ref = refs.parse_ref(ref_text)
    except ValueError as error:
        raise store.Conflict(str(error)) from error
    row = find_by_name(ref.source, deck_id)
    if row is None:
        raise store.NotFound(f"The data source \"{ref.source}\" is not in Lectern any more.")
    grid = sheet(row.id, ref.sheet)
    return row, ref, refs.read(grid["rows"], ref.range)
