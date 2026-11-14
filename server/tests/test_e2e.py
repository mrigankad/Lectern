"""Offline end to end through the HTTP API: create, outline, approve, build, render, critic, export."""
from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from .conftest import BOARD_PROMPT, build_deck, wait_for


def test_health_reports_offline_provider(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"ok": True, "provider": "offline"}


def test_full_flow(client: TestClient) -> None:
    created = client.post("/api/decks", json={"prompt": BOARD_PROMPT, "audience": "the board"})
    assert created.status_code == 200
    deck = created.json()
    assert deck["status"] == "draft" and deck["brief"]["prompt"] == BOARD_PROMPT
    assert deck["theme"]["font"] == "Urbanist" and deck["theme"]["colors"]["accent"] == "#2563EB"

    deck = wait_for(client, deck["id"], "draft")
    assert deck["status"] == "outline_ready"
    assert 6 <= len(deck["slides"]) <= 15
    assert deck["slides"][0]["layout"] == "title"
    assert all(s["status"] == "queued" and s["headline"] for s in deck["slides"])
    assert [s["index"] for s in deck["slides"]] == list(range(1, len(deck["slides"]) + 1))

    listed = client.get("/api/decks").json()
    assert listed[0]["id"] == deck["id"] and listed[0]["slide_count"] == len(deck["slides"])
    assert listed[0]["progress"] == {"ready": 0, "total": len(deck["slides"])}

    assert client.post(f"/api/decks/{deck['id']}/approve").json()["status"] == "building"
    deck = wait_for(client, deck["id"], "building")
    assert deck["status"] == "ready"
    assert all(s["status"] == "ready" and s["notes"] and s["score"] is not None for s in deck["slides"])
    for slide in deck["slides"]:
        headline_nodes = [n for n in slide["nodes"] if n["type"] == "text" and n["role"] == "headline"]
        assert len(headline_nodes) == 1 and headline_nodes[0]["value"] == slide["headline"]

    layouts = {s["layout"] for s in deck["slides"]}
    assert {"chart", "big_number"} <= layouts
    assert layouts & {"three_column", "process", "two_column", "next_steps", "timeline"}
    assert len(layouts) >= 6

    text = str(deck["slides"])
    for fact in ("34%", "2.6", "4.1", "$1.2M"):
        assert fact in text

    rendered = client.get(f"/api/decks/{deck['id']}/render").json()
    assert len(rendered) == len(deck["slides"])
    assert all(r["width"] == 1920 and r["height"] == 1080 and r["elements"] for r in rendered)
    one = client.get(f"/api/decks/{deck['id']}/slides/{deck['slides'][2]['id']}/render").json()
    assert one["id"] == deck["slides"][2]["id"] and one["index"] == 3

    report = client.get(f"/api/decks/{deck['id']}/critic").json()
    assert set(report) == {"score", "story", "design", "editability", "findings"}
    assert report["score"] >= 85 and report["editability"] == 100

    exported = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pptx", "include_notes": True})
    assert exported.status_code == 200
    out = exported.json()
    assert out["filename"].endswith(".pptx") and out["bytes"] > 10_000
    assert out["report"]["pictures"] == 0 and out["report"]["charts"] >= 1
    assert out["report"]["editable_objects"] == out["report"]["total_objects"]
    assert out["report"]["notes_slides"] == len(deck["slides"])
    assert all(check["ok"] for check in out["report"]["checks"])

    download = client.get(f"/api/files/{out['file_id']}")
    assert download.status_code == 200 and len(download.content) == out["bytes"]
    prs = Presentation(io.BytesIO(download.content))
    assert len(prs.slides) == len(deck["slides"])
    assert prs.slide_width == 12192000 and prs.slide_height == 6858000
    shapes = [shape for slide in prs.slides for shape in slide.shapes]
    assert not [s for s in shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert any(getattr(s, "has_chart", False) and s.has_chart for s in shapes)

    runs = client.get(f"/api/decks/{deck['id']}/runs").json()
    roles = {run["role"] for run in runs}
    assert {"strategist", "writer", "art_director", "renderer", "critic"} <= roles
    assert all(run["status"] == "done" and run["summary"].endswith(".") for run in runs)


def test_outline_edit_then_build(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    deck = wait_for(client, deck["id"], "draft")
    slides = deck["slides"]
    keep = [{"id": s["id"], "section": s.get("section"), "headline": s["headline"], "layout": s["layout"]}
            for s in slides[:4]]
    keep.reverse()
    keep.append({"headline": "The retention team owns the plan", "layout": "team"})
    updated = client.put(f"/api/decks/{deck['id']}/outline", json={"title": "Board review, Q3", "slides": keep})
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Board review, Q3" and len(body["slides"]) == 5
    assert [s["id"] for s in body["slides"][:4]] == [s["id"] for s in reversed(slides[:4])]
    assert body["slides"][4]["layout"] == "team" and body["slides"][4]["status"] == "queued"

    client.post(f"/api/decks/{deck['id']}/approve")
    built = wait_for(client, deck["id"], "building")
    assert built["status"] == "ready" and len(built["slides"]) == 5
    assert any(n["type"] == "items" for n in built["slides"][4]["nodes"])


def test_regenerate_outline_shorter(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    deck = wait_for(client, deck["id"], "draft")
    before = len(deck["slides"])
    again = client.post(f"/api/decks/{deck['id']}/outline/regenerate", json={"instruction": "make it shorter"})
    assert again.status_code == 200
    deck = wait_for(client, deck["id"], "draft")
    assert deck["status"] == "outline_ready" and len(deck["slides"]) < before


def test_manual_edit_relints_and_undo(client: TestClient) -> None:
    deck = build_deck(client)
    slide = next(s for s in deck["slides"] if s["layout"] == "summary")
    url = f"/api/decks/{deck['id']}/slides/{slide['id']}"
    patched = client.patch(url, json={"headline": "Summary", "notes": ""}).json()
    assert patched["headline"] == "Summary"
    assert next(n for n in patched["nodes"] if n.get("role") == "headline")["value"] == "Summary"
    assert patched["score"] < slide["score"]
    rules = {f["rule"] for f in client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
             if f["slide_id"] == slide["id"] and f["status"] == "open"}
    assert {"headline_not_claim", "missing_notes"} <= rules

    undone = client.post(f"{url}/undo").json()
    assert undone["headline"] == slide["headline"] and undone["notes"] == slide["notes"]
    assert undone["score"] == slide["score"]


def test_critic_fix_keep_reopen(client: TestClient) -> None:
    deck = build_deck(client)
    slide = next(s for s in deck["slides"] if s["layout"] == "summary")
    bullets = [f"Point number {n} is stated plainly" for n in range(1, 8)]
    client.patch(f"/api/decks/{deck['id']}/slides/{slide['id']}",
                 json={"headline": "Summary", "notes": "",
                       "nodes": [{"type": "bullets", "items": bullets}]})
    base = f"/api/decks/{deck['id']}/critic"
    findings = {f["rule"]: f for f in client.get(base).json()["findings"] if f["status"] == "open"}
    assert {"too_many_bullets", "headline_not_claim", "missing_notes"} <= set(findings)

    fixed = client.post(f"{base}/findings/{findings['too_many_bullets']['id']}", json={"action": "fix"}).json()
    assert fixed["status"] == "fixed"
    now = client.get(f"/api/decks/{deck['id']}").json()
    current = next(s for s in now["slides"] if s["id"] == slide["id"])
    assert len(next(n for n in current["nodes"] if n["type"] == "bullets")["items"]) == 5

    kept = client.post(f"{base}/findings/{findings['headline_not_claim']['id']}", json={"action": "keep"}).json()
    assert kept["status"] == "kept"
    rules = client.get("/api/rules").json()
    assert any(r["source"] == "critic:headline_not_claim" for r in rules)
    score_kept = client.get(base).json()["score"]

    reopened = client.post(f"{base}/findings/{findings['headline_not_claim']['id']}",
                           json={"action": "reopen"}).json()
    assert reopened["status"] == "open"
    assert not any(r["source"] == "critic:headline_not_claim" for r in client.get("/api/rules").json())
    assert client.get(base).json()["score"] < score_kept

    after = client.post(f"{base}/fix-all").json()
    assert not [f for f in after["findings"] if f["status"] == "open" and f["slide_id"] == slide["id"]]
    assert after["score"] >= score_kept


def test_ask_edits_slide_and_undo(client: TestClient) -> None:
    deck = build_deck(client)
    slide = next(s for s in deck["slides"] if s["layout"] == "summary")
    asked = client.post(f"/api/decks/{deck['id']}/ask",
                        json={"scope": "slide", "slide_id": slide["id"],
                              "message": "Change the headline to \"Churn is the one thing to fix\""})
    assert asked.status_code == 200
    message_id = asked.json()["message_id"]
    reply = _wait_message(client, deck["id"], message_id)
    assert reply["status"] == "done" and reply["role"] == "assistant" and reply["version_ids"]
    changed = client.get(f"/api/decks/{deck['id']}").json()
    assert next(s for s in changed["slides"] if s["id"] == slide["id"])["headline"] == "Churn is the one thing to fix"
    history = client.get(f"/api/decks/{deck['id']}/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant"]

    undone = client.post(f"/api/decks/{deck['id']}/slides/{slide['id']}/undo").json()
    assert undone["headline"] == slide["headline"]

    asked = client.post(f"/api/decks/{deck['id']}/ask", json={"scope": "deck", "message": "replace churn with attrition"})
    reply = _wait_message(client, deck["id"], asked.json()["message_id"])
    assert reply["status"] == "done" and len(reply["changed_slide_ids"]) >= 3
    assert "churn" not in str(client.get(f"/api/decks/{deck['id']}").json()["slides"]).lower()

    asked = client.post(f"/api/decks/{deck['id']}/ask",
                        json={"scope": "slide", "slide_id": slide["id"], "message": "make it sing"})
    reply = _wait_message(client, deck["id"], asked.json()["message_id"])
    assert reply["status"] == "done" and not reply["version_ids"] and "offline" in reply["result"].lower()


def _wait_message(client: TestClient, deck_id: str, message_id: str) -> dict:
    for _ in range(500):
        found = next(m for m in client.get(f"/api/decks/{deck_id}/messages").json() if m["id"] == message_id)
        if found["status"] != "pending":
            return found
        time.sleep(0.02)
    raise AssertionError("message stayed pending")


def test_rules_are_applied_and_linted(client: TestClient) -> None:
    rule = client.post("/api/rules", json={"text": "Never use the word \"churn\""}).json()
    assert rule["id"] and rule["text"]
    deck = build_deck(client)
    assert "churn" not in str(deck["slides"]).lower()

    slide = deck["slides"][2]
    client.patch(f"/api/decks/{deck['id']}/slides/{slide['id']}", json={"notes": "Talk about churn here."})
    findings = client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
    assert any(f["rule"] == "rule_violation" and f["severity"] == "high" for f in findings)

    assert client.delete(f"/api/rules/{rule['id']}").status_code == 200
    assert client.get("/api/rules").json() == []
    findings = client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
    assert not [f for f in findings if f["rule"] == "rule_violation" and f["status"] == "open"]


def test_errors_are_plain_json(client: TestClient) -> None:
    missing = client.get("/api/decks/nope")
    assert missing.status_code == 404 and isinstance(missing.json()["detail"], str)
    invalid = client.post("/api/decks", json={})
    assert invalid.status_code == 422 and isinstance(invalid.json()["detail"], str)
    deck = client.post("/api/decks", json={"prompt": "A short update"}).json()
    early = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pptx", "include_notes": True})
    assert early.status_code in (200, 409)
    assert client.get("/api/files/fl_000000000000").status_code == 404
    assert client.delete(f"/api/decks/{deck['id']}").json() == {"ok": True}
    assert client.get(f"/api/decks/{deck['id']}").status_code == 404


def test_layout_registry_endpoint(client: TestClient) -> None:
    layouts = client.get("/api/layouts").json()
    assert len(layouts) == 21
    ids = {layout["id"] for layout in layouts}
    assert {"title", "big_number", "chart", "three_column", "appendix"} <= ids
    for layout in layouts:
        assert layout["name"] and layout["purpose"]
        assert layout["slots"][0]["name"] == "headline" and layout["slots"][0]["required"] is True


def test_undo_an_ask_reverts_only_its_own_versions(client: TestClient) -> None:
    """QA: Undo after a deck-wide Ask reverted an earlier manual notes edit. The rule: an Ask's Undo puts
    back only the fields that Ask changed, and keeps any later edit to the same field."""
    deck = build_deck(client)
    base = f"/api/decks/{deck['id']}"
    churn = [s for s in deck["slides"] if "churn" in s["headline"].lower()]
    first, second = churn[0], churn[1]
    client.patch(f"{base}/slides/{first['id']}", json={"notes": "My own note, written by hand."})
    asked = client.post(f"{base}/ask", json={"scope": "deck", "message": "replace churn with attrition"})
    reply = _wait_message(client, deck["id"], asked.json()["message_id"])
    assert first["id"] in reply["changed_slide_ids"] and second["id"] in reply["changed_slide_ids"]
    # A manual edit after the Ask, on a field the Ask also changed.
    client.patch(f"{base}/slides/{second['id']}", json={"headline": "Attrition is what we fix next"})

    result = client.post(f"{base}/messages/{reply['id']}/undo")
    assert result.status_code == 200, result.text
    assert {"slide_id": second["id"], "field": "headline", "reason": "changed since"} in result.json()["kept"]
    slides = {s["id"]: s for s in client.get(base).json()["slides"]}
    assert slides[first["id"]]["headline"] == first["headline"]              # the Ask's change is gone
    assert slides[first["id"]]["notes"] == "My own note, written by hand."   # the earlier edit stays
    assert slides[second["id"]]["headline"] == "Attrition is what we fix next"  # the later edit stays
    others = [s for s in churn[2:] if s["id"] in reply["changed_slide_ids"]]
    assert all(slides[s["id"]]["headline"] == s["headline"] for s in others)
    message = next(m for m in client.get(f"{base}/messages").json() if m["id"] == reply["id"])
    assert message["undone"]
    assert client.post(f"{base}/messages/{reply['id']}/undo").status_code == 409

    # Slide Undo steps back one version: the revert itself, never past the hand-written note.
    stepped = client.post(f"{base}/slides/{first['id']}/undo").json()
    assert stepped["notes"] == "My own note, written by hand." and "ttrition" in stepped["headline"]
