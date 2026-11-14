"""The Strategist interview (U04) and share links (U14)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import BOARD_PROMPT, build_deck, wait_for


def test_create_without_interview_keeps_old_flow(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    assert deck["status"] == "draft"
    assert client.get(f"/api/decks/{deck['id']}/interview").status_code == 404


def test_interview_answers_feed_the_outline(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT, "interview": True}).json()
    assert deck["status"] == "interview"
    state = client.get(f"/api/decks/{deck['id']}/interview").json()
    assert [q["key"] for q in state["questions"]] == ["audience", "goal", "minutes"]
    assert "Board of directors" in state["questions"][0]["chips"]
    assert any("1.2M" in chip for chip in state["questions"][1]["chips"])
    assert {n["value"] for n in state["understood"]["numbers"]} & {"+34%", "4.1%"}
    assert state["current"] == "q1"
    # Answers stay in the interview until the last one.
    state = client.post(f"/api/decks/{deck['id']}/interview/answer",
                        json={"question_id": "q1", "answer": "Board of directors, seven people"}).json()
    assert state["understood"]["audience"] == "Board of directors, seven people"
    assert state["current"] == "q2"
    assert client.get(f"/api/decks/{deck['id']}").json()["status"] == "interview"
    state = client.post(f"/api/decks/{deck['id']}/interview/skip", json={"question_id": "q2"}).json()
    assert state["current"] == "q3"
    state = client.post(f"/api/decks/{deck['id']}/interview/answer",
                        json={"question_id": "q3", "answer": "About 20 minutes"}).json()
    assert state["status"] == "done"
    final = wait_for(client, deck["id"], "draft")
    assert final["status"] == "outline_ready"
    assert final["brief"]["audience"] == "Board of directors, seven people"
    assert final["brief"]["minutes"] == 20
    assert client.post(f"/api/decks/{deck['id']}/interview/answer",
                       json={"question_id": "q1", "answer": "x"}).status_code == 409


def test_interview_skip_all(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT, "interview": True}).json()
    state = client.post(f"/api/decks/{deck['id']}/interview/skip", json={"all": True}).json()
    assert state["status"] == "done"
    assert wait_for(client, deck["id"], "draft")["status"] == "outline_ready"


def test_interview_does_not_ask_what_the_brief_says(client: TestClient) -> None:
    """QA: "Who is in the room?" was asked although the new-deck page had set the audience."""
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT, "interview": True,
                                           "audience": "Board of directors"}).json()
    state = client.get(f"/api/decks/{deck['id']}/interview").json()
    first = state["questions"][0]
    assert first["key"] == "audience" and first["answer"] == "Board of directors" and first["from_brief"]
    assert state["current"] == "q2" and state["understood"]["audience"] == "Board of directors"
    # "Change" re-answers it while the interview is open.
    state = client.post(f"/api/decks/{deck['id']}/interview/answer",
                        json={"question_id": "q1", "answer": "Board and two investors"}).json()
    assert state["questions"][0]["from_brief"] is False and state["current"] == "q2"

    # Everything in the brief: nothing to ask, the outline starts straight away.
    full = client.post("/api/decks", json={"prompt": BOARD_PROMPT, "interview": True, "audience": "Board",
                                           "goal": "Approve the budget", "minutes": 15}).json()
    state = client.get(f"/api/decks/{full['id']}/interview").json()
    assert state["status"] == "done" and all(q["from_brief"] for q in state["questions"])
    final = wait_for(client, full["id"], "draft")
    assert final["status"] == "outline_ready" and final["brief"]["minutes"] == 15


def test_share_link_flow(client: TestClient) -> None:
    deck = build_deck(client)
    did = deck["id"]
    link = client.post(f"/api/decks/{did}/shares", json={"allow_download": True}).json()
    assert link["path"] == f"/s/{link['token']}" and link["stats"]["opens"] == 0
    token = link["token"]
    assert client.get(f"/api/public/shares/{token}").json()["requires_password"] is False
    opened = client.post(f"/api/public/shares/{token}/open", json={"visitor": "v1"}).json()
    assert len(opened["render"]) == len(deck["slides"])
    assert all("notes" not in s for s in opened["slides"])
    first = opened["slides"][0]["id"]
    assert client.post(f"/api/public/shares/{token}/views/{opened['view_id']}/ping",
                       json={"slide_id": first, "seconds": 12}).status_code == 200
    res = client.get(f"/api/public/shares/{token}/download", params={"view_id": opened["view_id"]})
    assert res.status_code == 200 and res.content[:2] == b"PK"
    stats = client.get(f"/api/decks/{did}/shares").json()[0]["stats"]
    assert stats["opens"] == 1 and stats["total_seconds"] == 12
    assert stats["most_viewed"]["slide_id"] == first

    # Password, notes, no download.
    upd = client.patch(f"/api/decks/{did}/shares/{link['id']}",
                       json={"access": "password", "password": "hunter22", "show_notes": True,
                             "allow_download": False}).json()
    assert upd["has_password"] and "password_hash" not in upd
    assert client.post(f"/api/public/shares/{token}/open", json={}).status_code == 403
    assert client.post(f"/api/public/shares/{token}/open", json={"password": "nope"}).status_code == 403
    opened = client.post(f"/api/public/shares/{token}/open", json={"password": "hunter22"}).json()
    assert any(s.get("notes") for s in opened["slides"])
    assert client.get(f"/api/public/shares/{token}/download",
                      params={"view_id": opened["view_id"]}).status_code == 403

    from lectern.db import session
    from lectern.models import ShareLinkRow
    with session() as s:
        stored = s.get(ShareLinkRow, link["id"])
        assert stored is not None and "hunter22" not in (stored.password_hash or "")

    assert client.delete(f"/api/decks/{did}/shares/{link['id']}").status_code == 200
    assert client.get(f"/api/public/shares/{token}").status_code == 404


def test_expired_link(client: TestClient) -> None:
    deck = build_deck(client)
    link = client.post(f"/api/decks/{deck['id']}/shares", json={"expires_in_days": 1}).json()
    from lectern.db import session
    from lectern.models import ShareLinkRow
    with session() as s:
        row = s.get(ShareLinkRow, link["id"])
        assert row is not None
        row.expires_at = "2000-01-01T00:00:00Z"
        s.add(row)
        s.commit()
    assert client.get(f"/api/public/shares/{link['token']}").status_code == 404
