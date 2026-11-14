from fastapi.testclient import TestClient


def test_patch_deck_icon_and_title(client: TestClient) -> None:
    deck = client.post("/api/decks", json={"prompt": "Quarterly review: revenue up 12%."}).json()
    r = client.patch(f"/api/decks/{deck['id']}", json={"icon": "rocket", "icon_color": "blue", "title": "Q review"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["icon"] == "rocket" and body["icon_color"] == "blue" and body["title"] == "Q review"
    listed = next(d for d in client.get("/api/decks").json() if d["id"] == deck["id"])
    assert listed["icon"] == "rocket" and listed["icon_color"] == "blue"
    cleared = client.patch(f"/api/decks/{deck['id']}", json={"icon": ""}).json()
    assert "icon" not in cleared and cleared["icon_color"] == "blue"
