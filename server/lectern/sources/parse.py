"""Parse a data source into sheets (a grid of display strings with A1 addresses) or text chunks.

Spreadsheets keep the value as the reader sees it ("4.1%", "$412k", "1,204"); numbers are read back from
that text by `number_of`, so a slide, the lint and the preview all agree on what a cell says.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

MAX_ROWS = 1000
MAX_COLS = 60
CHUNK_CHARS = 900

KIND_BY_EXT = {
    "xlsx": "xlsx", "xlsm": "xlsx", "csv": "csv", "tsv": "csv", "pdf": "pdf", "docx": "docx",
    "txt": "text", "md": "text", "markdown": "text",
}


class ParseError(ValueError):
    """The file could not be read; the message is shown to the user."""


def kind_for(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return KIND_BY_EXT.get(ext)


# ---------------------------------------------------------------- numbers in cells
_NUM = re.compile(r"^\s*(?P<neg>-|\()?\s*(?P<cur>[$€£₹])?\s*(?P<sign>[-+])?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d*\.?\d+)"
                  r"\s*(?P<scale>[kKmMbB]|bn)?\s*(?P<suf>%|pts?|pp|x)?\s*\)?\s*$")
_SCALE = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}


def number_of(text: Any) -> tuple[float, str] | None:
    """(value as displayed, unit) for a cell's text, or None when it is not a number.

    "4.1%" -> (4.1, "%"), "$412k" -> (412000, "$"), "1,204" -> (1204, ""), "+1.5 pts" -> (1.5, "pts").
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text), ""
    match = _NUM.match(str(text or ""))
    if not match:
        return None
    value = float(match.group("num").replace(",", ""))
    value *= _SCALE.get((match.group("scale") or "").lower(), 1.0)
    if match.group("neg") or match.group("sign") == "-":
        value = -value
    unit = match.group("cur") or (match.group("suf") or "").lower()
    if unit in {"pt", "pp"}:
        unit = "pts"
    return value, unit


def _fmt_number(value: float, number_format: str = "General") -> str:
    fmt = number_format or "General"
    if "%" in fmt:
        decimals = len(fmt.split(".")[1].split("%")[0]) if "." in fmt else 0
        return f"{value * 100:.{decimals}f}%"
    prefix = "$" if "$" in fmt else "€" if "€" in fmt else "£" if "£" in fmt else ""
    if "." in fmt and fmt != "General":
        decimals = len(re.split(r"[^0#]", fmt.split(".")[1])[0])
        body = f"{abs(value):,.{decimals}f}" if "," in fmt else f"{abs(value):.{decimals}f}"
    elif float(value).is_integer():
        body = f"{abs(int(value)):,}" if ("," in fmt or abs(value) >= 10000) else f"{abs(int(value))}"
    else:
        body = f"{abs(value):.10g}"
    return ("-" if value < 0 else "") + prefix + body


def _cell_text(value: Any, number_format: str = "General") -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return _fmt_number(float(value), number_format)
    if isinstance(value, datetime):
        return value.strftime("%b %Y") if value.day == 1 else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _trim(rows: list[list[str]]) -> list[list[str]]:
    rows = [row[:MAX_COLS] for row in rows[:MAX_ROWS]]
    while rows and not any(rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, c in enumerate(row) if c), default=0) for row in rows), default=0)
    return [row[:width] + [""] * (width - len(row[:width])) for row in rows]


# ---------------------------------------------------------------- spreadsheets
def parse_xlsx(data: bytes) -> dict[str, Any]:
    try:
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as error:  # noqa: BLE001  (openpyxl raises many kinds)
        raise ParseError("This Excel file could not be opened. Save it as .xlsx and try again.") from error
    sheets = []
    for sheet in book.worksheets:
        rows: list[list[str]] = []
        for row in sheet.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLS):
            rows.append([_cell_text(cell.value, getattr(cell, "number_format", "General")) for cell in row])
        sheets.append({"name": sheet.title, "rows": _trim(rows)})
    book.close()
    if not sheets:
        raise ParseError("This workbook has no sheets.")
    return {"sheets": sheets, "chunks": []}


def parse_csv(data: bytes, name: str) -> dict[str, Any]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), dialect)]
    if not rows:
        raise ParseError("This CSV file is empty.")
    return {"sheets": [{"name": sheet_name_for(name), "rows": _trim(rows)}], "chunks": []}


def sheet_name_for(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return re.sub(r"[!\[\]:*?/\\]", " ", stem).strip()[:31] or "Sheet1"


# ---------------------------------------------------------------- documents
def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _chunk(paragraphs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Group (ref, text) paragraphs into chunks of about CHUNK_CHARS, keeping the first ref of each."""
    chunks: list[dict[str, str]] = []
    ref, buf = "", ""
    for where, text in paragraphs:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if buf and len(buf) + len(text) > CHUNK_CHARS:
            chunks.append({"ref": ref, "text": buf})
            buf = ""
        if not buf:
            ref = where
        buf = f"{buf}\n{text}" if buf else text
    if buf:
        chunks.append({"ref": ref, "text": buf})
    return chunks


def parse_pdf(data: bytes) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [(f"p.{i}", page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    except Exception as error:  # noqa: BLE001
        raise ParseError("This PDF could not be read. It may be encrypted or damaged.") from error
    chunks = []
    for ref, text in pages:  # never merge pages: a fact cites one page
        chunks.extend(_chunk([(ref, para) for para in re.split(r"\n\s*\n", text)]))
    if not chunks:
        raise ParseError("This PDF has no text Lectern can read (it may be scanned images).")
    return {"sheets": [], "chunks": chunks, "pages": len(pages)}


def parse_docx(data: bytes) -> dict[str, Any]:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
    except Exception as error:  # noqa: BLE001
        raise ParseError("This Word file could not be opened. Save it as .docx and try again.") from error
    paragraphs = [(f"para {i}", p.text) for i, p in enumerate(doc.paragraphs, start=1)]
    sheets = []
    for t, table in enumerate(doc.tables, start=1):
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        sheets.append({"name": f"Table {t}", "rows": _trim(rows)})
    return {"sheets": sheets, "chunks": _chunk(paragraphs)}


def parse_text(data: bytes) -> dict[str, Any]:
    text = _decode(data)
    paragraphs: list[tuple[str, str]] = []
    line_no = 1
    for block in re.split(r"(\n\s*\n)", text):
        if block.strip():
            paragraphs.append((f"line {line_no}", block))
        line_no += block.count("\n")
    return {"sheets": [], "chunks": _chunk(paragraphs)}


class _TextOfHtml(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "br", "section", "article", "td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if not self.depth:
            self.parts.append(data)


def parse_html(html: str) -> dict[str, Any]:
    parser = _TextOfHtml()
    parser.feed(html)
    text = "".join(parser.parts)
    paragraphs = [(f"para {i}", p) for i, p in enumerate((p for p in re.split(r"\n\s*\n", text) if p.strip()), 1)]
    return {"sheets": [], "chunks": _chunk(paragraphs), "title": re.sub(r"\s+", " ", parser.title).strip()}


def parse(kind: str, data: bytes, name: str) -> dict[str, Any]:
    if kind == "xlsx":
        return parse_xlsx(data)
    if kind in {"csv", "gsheet"}:
        return parse_csv(data, name)
    if kind == "pdf":
        return parse_pdf(data)
    if kind == "docx":
        return parse_docx(data)
    if kind == "text":
        return parse_text(data)
    if kind == "url":
        return parse_html(_decode(data))
    raise ParseError("Lectern reads XLSX, CSV, PDF, DOCX, TXT and Markdown files.")
