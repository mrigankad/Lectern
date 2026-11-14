"""Data sources: upload and parse, the Analyst, linked charts and stats, refresh, lint against cells, export."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pptx import Presentation

from .conftest import build_deck

MONTHS = [("Apr", 2.6, 412000, 1204), ("May", 2.8, 431000, 1231), ("Jun", 3.1, 455000, 1262),
          ("Jul", 3.4, 489000, 1280), ("Aug", 3.8, 521000, 1291), ("Sep", 4.1, 552000, 1297)]


def workbook(churn: list[float] | None = None) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Churn"
    sheet.append(["Month", "Churn %", "Revenue", "Logos"])
    for i, (month, rate, revenue, logos) in enumerate(MONTHS):
        sheet.append([month, churn[i] if churn else rate, revenue, logos])
    for cell in sheet["C"][1:]:
        cell.number_format = '"$"#,##0'
    sheet.append([])
    sheet.append(["Change", "+1.5 pts", "+34%", "+93"])
    other = book.create_sheet("Pipeline")
    other.append(["Stage", "Deals"])
    for stage, deals in (("Lead", 120), ("Qualified", 64), ("Proposal", 22)):
        other.append([stage, deals])
    data = io.BytesIO()
    book.save(data)
    return data.getvalue()


def upload(client: TestClient, data: bytes, name: str, deck_id: str | None = None) -> dict[str, Any]:
    params = {"filename": name, **({"deck_id": deck_id} if deck_id else {})}
    response = client.post("/api/sources/upload", params=params, content=data)
    assert response.status_code == 200, response.text
    return response.json()


def chart_slide(deck: dict[str, Any]) -> dict[str, Any]:
    return next(s for s in deck["slides"] if s["layout"] == "chart")


# ---------------------------------------------------------------- parsing
def test_xlsx_upload_preview_with_cell_values(client: TestClient) -> None:
    source = upload(client, workbook(), "q3-financials.xlsx")
    assert source["kind"] == "xlsx" and source["status"] == "ready"
    assert [s["name"] for s in source["summary"]["sheets"]] == ["Churn", "Pipeline"]
    preview = client.get(f"/api/sources/{source['id']}/preview").json()
    assert preview["sheet"] == "Churn"
    assert preview["rows"][0] == ["Month", "Churn %", "Revenue", "Logos"]
    assert preview["rows"][6] == ["Sep", "4.1", "$552,000", "1297"]
    other = client.get(f"/api/sources/{source['id']}/preview", params={"sheet": "Pipeline"}).json()
    assert other["rows"][3] == ["Proposal", "22"]
    assert client.get("/api/sources").json()[0]["id"] == source["id"]


def test_csv_docx_text_and_bad_files(client: TestClient) -> None:
    csv_source = upload(client, b"Region,Share %\nNorth,40\nSouth,35\nWest,25\n", "regions.csv")
    preview = client.get(f"/api/sources/{csv_source['id']}/preview").json()
    assert preview["sheet"] == "regions" and preview["rows"][1] == ["North", "40"]
    suggestion = client.post(f"/api/sources/{csv_source['id']}/suggest", json={"range": "A1:B4"}).json()
    assert suggestion["kind"] == "pie" and suggestion["data_ref"] == "regions.csv!regions!A1:B4"

    from docx import Document
    doc = Document()
    doc.add_paragraph("Board notes for Q3.")
    doc.add_paragraph("Monthly logo churn reached 4.1% in September, up from 2.6% in April.")
    data = io.BytesIO()
    doc.save(data)
    docx_source = upload(client, data.getvalue(), "board-notes.docx")
    chunks = client.get(f"/api/sources/{docx_source['id']}/preview").json()["chunks"]
    assert chunks and chunks[0]["ref"] == "para 1" and "4.1%" in chunks[0]["text"]
    facts = client.get(f"/api/sources/{docx_source['id']}/analysis").json()["facts"]
    assert any(f["value"] == "4.1%" and f["ref"] == "board-notes.docx para 1" for f in facts)

    text_source = upload(client, b"# Notes\n\nRevenue grew 34% this quarter.\n", "notes.md")
    assert text_source["kind"] == "text"

    bad = client.post("/api/sources/upload", params={"filename": "photo.png"}, content=b"x")
    assert bad.status_code == 409 and "XLSX" in bad.json()["detail"]
    broken = client.post("/api/sources/upload", params={"filename": "broken.xlsx"}, content=b"not a zip")
    assert broken.status_code == 409


def test_links_and_google_sheets(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from lectern.sources import service

    calls: list[str] = []

    def fake(url: str) -> tuple[bytes, str]:
        calls.append(url)
        if "docs.google.com" in url:
            return b"Quarter,Revenue\nQ1,10\nQ2,12\nQ3,15\n", "text/csv"
        return (b"<html><head><title>Churn report</title><script>x=1</script></head><body><p>Churn rose to "
                b"4.1% in September.</p></body></html>", "text/html")

    monkeypatch.setattr(service, "fetcher", fake)
    page = client.post("/api/sources/link", json={"url": "https://example.com/report"}).json()
    assert page["kind"] == "url" and page["summary"]["title"] == "Churn report"
    chunks = client.get(f"/api/sources/{page['id']}/preview").json()["chunks"]
    assert "4.1%" in chunks[0]["text"] and "x=1" not in chunks[0]["text"]

    sheet = client.post("/api/sources/link", json={
        "url": "https://docs.google.com/spreadsheets/d/abc123XYZ/edit#gid=42"}).json()
    assert sheet["kind"] == "gsheet"
    assert calls[-1] == "https://docs.google.com/spreadsheets/d/abc123XYZ/export?format=csv&gid=42"
    suggestion = client.post(f"/api/sources/{sheet['id']}/suggest", json={"range": "A1:B4"}).json()
    assert suggestion["kind"] == "line" and suggestion["series"][0]["values"] == [10, 12, 15]

    monkeypatch.setattr(service, "fetcher", lambda url: (b"<!DOCTYPE html><html>Sign in</html>", "text/html"))
    private = client.post("/api/sources/link", json={"url": "https://docs.google.com/spreadsheets/d/zzz/edit"})
    assert private.status_code == 409 and "Anyone with the link" in private.json()["detail"]
    assert client.post("/api/sources/link", json={"url": "not a url"}).status_code == 409


# ---------------------------------------------------------------- analyst
def test_suggestions_follow_the_chart_rules(client: TestClient) -> None:
    source = upload(client, workbook(), "q3-financials.xlsx")
    churn = client.post(f"/api/sources/{source['id']}/suggest", json={"sheet": "Churn", "range": "A1:B7"}).json()
    assert churn["kind"] == "line" and churn["unit"] == "%"
    assert churn["categories"] == ["Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    assert churn["headline"] == "Churn rose from 2.6% to 4.1%"
    assert churn["data_ref"] == "q3-financials.xlsx!Churn!A1:B7" and churn["cells_label"] == "Churn, A1 to B7"
    assert "direction" in churn["reason"]
    pie = next(a for a in churn["alternatives"] if a["kind"] == "pie")
    assert pie["ok"] is False

    stages = client.post(f"/api/sources/{source['id']}/suggest", json={"sheet": "Pipeline", "range": "A1:B4"}).json()
    assert stages["kind"] == "bar" and "categories" in stages["reason"]
    two = client.post(f"/api/sources/{source['id']}/suggest", json={"range": "A1:B3"}).json()
    assert two["kind"] == "bar"   # two periods are too few for a line
    words = client.post(f"/api/sources/{source['id']}/suggest", json={"range": "A1:A7"}).json()
    assert words["ok"] is False

    analysis = client.get(f"/api/sources/{source['id']}/analysis").json()
    assert analysis["charts"][0]["data_ref"] == "q3-financials.xlsx!Churn!A1:B7"   # summary row left out
    change = next(f for f in analysis["facts"] if f["kind"] == "change" and f["label"] == "Churn")
    assert change["from"] == "2.6%" and change["value"] == "4.1%" and change["good"] is False
    assert change["ref"] == "q3-financials.xlsx!Churn!B2:B7"
    latest = next(f for f in analysis["facts"] if f["kind"] == "number" and f["label"].startswith("Revenue"))
    assert latest["ref"] == "q3-financials.xlsx!Churn!C7" and latest["value"] == "$552k"


def test_the_analyst_feeds_the_deck(client: TestClient) -> None:
    source = upload(client, workbook(), "q3-financials.xlsx")
    deck = build_deck(client, "Our Q3 board review. I need the board to approve a $1.2M retention budget.",
                      source_ids=[source["id"]])
    assert client.get("/api/sources", params={"deck_id": deck["id"]}).json()[0]["id"] == source["id"]
    facts = deck["brief"]["data_facts"]
    assert any(f.get("ref") == "q3-financials.xlsx!Churn!B7" for f in facts)
    runs = client.get(f"/api/decks/{deck['id']}/runs").json()
    assert any(r["role"] == "analyst" and r["status"] == "done" for r in runs)
    charts = [n for s in deck["slides"] for n in s["nodes"] if n["type"] == "chart"]
    linked = [n for n in charts if n.get("data_ref") == "q3-financials.xlsx!Churn!A1:B7"]
    assert linked and linked[0]["series"][0]["values"] == [2.6, 2.8, 3.1, 3.4, 3.8, 4.1]
    assert linked[0]["kind"] == "line"


def test_prompts_carry_the_facts() -> None:
    from lectern.agents import prompts

    text = prompts.brief_block({"prompt": "Q3", "data_facts": [
        {"kind": "change", "label": "Churn", "from": "2.6%", "value": "4.1%", "direction": "up",
         "ref": "q.xlsx!Churn!B2:B7"},
        {"kind": "chart", "data_ref": "q.xlsx!Churn!A1:B7", "chart": "line", "headline": "Churn rose",
         "reason": "Over time."}]})
    assert "Churn rose from 2.6% to 4.1%. [q.xlsx!Churn!B2:B7]" in text
    assert "data_ref q.xlsx!Churn!A1:B7" in text


# ---------------------------------------------------------------- linked charts and stats
def test_insert_refresh_lint_and_export(client: TestClient, tmp_path: Path) -> None:
    deck = build_deck(client)
    slide = chart_slide(deck)
    source = upload(client, workbook(), "q3-financials.xlsx", deck["id"])
    base = f"/api/decks/{deck['id']}/slides/{slide['id']}"

    inserted = client.post(f"{base}/data/insert", json={"data_ref": "q3-financials.xlsx!Churn!A1:B7",
                                                        "kind": "line"}).json()
    chart = next(n for n in inserted["nodes"] if n["type"] == "chart")
    assert chart["data_ref"] == "q3-financials.xlsx!Churn!A1:B7" and chart["kind"] == "line"
    assert chart["series"][0]["values"][-1] == 4.1
    assert client.get(f"{base}/data").json()["linked"][0]["data_ref"] == chart["data_ref"]

    # The notes drift from the sheet: the lint names the cell, and "Update slide" fixes them.
    client.patch(base, json={"notes": "Churn reached 4.2% in September, the highest this year."})
    findings = [f for f in client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
                if f["slide_id"] == slide["id"] and f["rule"] == "number_mismatch" and f["status"] == "open"]
    assert findings and "4.2%" in findings[0]["detail"] and "4.1" in findings[0]["detail"]
    fixed = client.post(f"{base}/data/fix-numbers").json()
    assert fixed["fixed"] == 1 and "4.1%" in fixed["slide"]["notes"]
    assert not client.get(f"{base}/data").json()["mismatches"]

    # The sheet changes: the chart is flagged, then refresh brings it in line.
    new = [2.6, 2.7, 2.9, 3.0, 3.3, 3.6]
    assert client.put(f"/api/sources/{source['id']}/file", content=workbook(new)).status_code == 200
    data = client.get(f"{base}/data").json()
    assert any("does not match its sheet" in m["title"] for m in data["mismatches"])
    refreshed = client.post(f"{base}/data/refresh").json()
    assert refreshed["changed"] == ["q3-financials.xlsx!Churn!A1:B7"]
    chart = next(n for n in refreshed["slide"]["nodes"] if n["type"] == "chart")
    assert chart["series"][0]["values"] == new

    # PowerPoint keeps the chart native, with the sheet's numbers.
    out = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pptx", "include_notes": True}).json()
    pptx = tmp_path / "deck.pptx"
    pptx.write_bytes(client.get(f"/api/files/{out['file_id']}").content)
    page = Presentation(str(pptx)).slides[slide["index"] - 1]
    charts = [s for s in page.shapes if s.has_chart]
    assert charts and list(charts[0].chart.plots[0].series[0].values) == new


def test_linked_stat(client: TestClient) -> None:
    deck = build_deck(client)
    slide = deck["slides"][1]
    source = upload(client, workbook(), "q3-financials.xlsx", deck["id"])
    base = f"/api/decks/{deck['id']}/slides/{slide['id']}"
    result = client.post(f"{base}/data/insert", json={"data_ref": "q3-financials.xlsx!Churn!B2:B7", "as": "stat"})
    assert result.status_code == 200, result.text
    stat = next(n for n in result.json()["nodes"] if n["type"] == "stat")
    assert stat["value"] == "4.1" and stat["source"] == "q3-financials.xlsx!Churn!B7"
    assert result.json()["layout"] == "big_number"
    client.put(f"/api/sources/{source['id']}/file", content=workbook([2.6, 2.7, 2.9, 3.0, 3.3, 3.9]))
    refreshed = client.post(f"{base}/data/refresh").json()
    assert next(n for n in refreshed["slide"]["nodes"] if n["type"] == "stat")["value"] == "3.9"


def test_bad_refs_and_missing_links(client: TestClient) -> None:
    deck = build_deck(client)
    slide = chart_slide(deck)
    base = f"/api/decks/{deck['id']}/slides/{slide['id']}"
    assert client.post(f"{base}/data/insert", json={"data_ref": "nope"}).status_code == 409
    assert client.post(f"{base}/data/insert", json={"data_ref": "gone.xlsx!S!A1:B2"}).status_code == 404
    assert client.post(f"{base}/data/refresh").status_code == 409
    source = upload(client, workbook(), "q3-financials.xlsx", deck["id"])
    assert client.delete(f"/api/sources/{source['id']}").json() == {"ok": True}
    assert client.get(f"/api/sources/{source['id']}").status_code == 404


def test_refs() -> None:
    from lectern.sources import refs

    ref = refs.parse_ref("q3 financials.xlsx!'My sheet'!b7:A1")
    assert (ref.source, ref.sheet, ref.range.a1, ref.range.label) == ("q3 financials.xlsx", "My sheet", "A1:B7",
                                                                      "A1 to B7")
    assert refs.col_name(27) == "AB" and refs.col_index("AB") == 27
    assert not refs.looks_like_ref("Source: figures from the brief")


def test_refresh_updates_the_numbers_written_from_the_old_cells(client: TestClient) -> None:
    """QA: after "Refresh from sheet" the chart moved to 3.6 but the headline still said 4.1, and the lint
    stayed quiet because the headline's figures had no unit."""
    deck = build_deck(client)
    slide = chart_slide(deck)
    source = upload(client, workbook(), "q3-financials.xlsx", deck["id"])
    base = f"/api/decks/{deck['id']}/slides/{slide['id']}"
    client.post(f"{base}/data/insert", json={"data_ref": "q3-financials.xlsx!Churn!A1:B7", "kind": "line"})
    client.patch(base, json={"headline": "Churn rose from 2.6 to 4.1 in six months",
                             "notes": "September churn was 4.1%, the highest this year."})

    # A bare figure that drifted from the linked chart is a mismatch too.
    client.patch(base, json={"headline": "Churn rose from 2.6 to 4.0 in six months"})
    assert any("4.0" in m["detail"] for m in client.get(f"{base}/data").json()["mismatches"])
    client.patch(base, json={"headline": "Churn rose from 2.6 to 4.1 in six months"})
    assert not client.get(f"{base}/data").json()["mismatches"]

    client.put(f"/api/sources/{source['id']}/file", content=workbook([2.6, 2.7, 2.9, 3.0, 3.3, 3.6]))
    offered = client.post(f"{base}/data/refresh", params={"update_text": "false"}).json()
    assert offered["text_updates"] == {"4.1": "3.6", "4.1%": "3.6%"}
    assert "4.1" in offered["slide"]["headline"] and offered["mismatches"]
    # Declined, the drift stays visible to the lint and "Update slide" fixes it.
    fixed = client.post(f"{base}/data/fix-numbers").json()["slide"]
    assert fixed["headline"] == "Churn rose from 2.6 to 3.6 in six months" and "3.6%" in fixed["notes"]

    client.put(f"/api/sources/{source['id']}/file", content=workbook([2.6, 2.7, 2.9, 3.0, 3.3, 3.7]))
    refreshed = client.post(f"{base}/data/refresh").json()
    assert refreshed["slide"]["headline"] == "Churn rose from 2.6 to 3.7 in six months"
    assert refreshed["slide"]["notes"] == "September churn was 3.7%, the highest this year."
    assert not refreshed["mismatches"] and not refreshed["flagged"]
