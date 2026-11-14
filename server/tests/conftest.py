"""Test setup: a fresh data directory per test, no artificial delay, and no provider keys from the shell."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
             "MISTRAL_API_KEY", "GEMINI_API_KEY", "FAL_KEY", "RUNWAYML_API_SECRET", "PEXELS_API_KEY"):
    os.environ.pop(name, None)
os.environ["LECTERN_OFFLINE_DELAY"] = "0"

BOARD_PROMPT = ("Our Q3 board review. Revenue is up 34%, but monthly logo churn went from 2.6% to 4.1%. "
                "I need the board to approve a $1.2M retention budget.")


@pytest.fixture()
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from lectern import db
    from lectern.llm import router

    monkeypatch.setenv("LECTERN_DATA_DIR", str(tmp_path))
    db.reset_engine()
    router.set_provider_override(None)
    from lectern.media import router as media_router

    media_router.clear_overrides()
    yield tmp_path
    media_router.clear_overrides()
    router.set_provider_override(None)
    db.reset_engine()


@pytest.fixture()
def client(data_dir: Path) -> Iterator[TestClient]:
    from lectern.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def wait_for(client: TestClient, deck_id: str, leaving: str, timeout: float = 30.0) -> dict[str, Any]:
    """Poll the deck until its status is no longer `leaving`."""
    deadline = time.time() + timeout
    deck: dict[str, Any] = {}
    while time.time() < deadline:
        deck = client.get(f"/api/decks/{deck_id}").json()
        if deck["status"] != leaving:
            return deck
        time.sleep(0.02)
    raise AssertionError(f"deck stayed {leaving}: {deck}")


def build_deck(client: TestClient, prompt: str = BOARD_PROMPT, **brief: Any) -> dict[str, Any]:
    """Create a deck, wait for the outline, approve it and wait until it is built."""
    deck = client.post("/api/decks", json={"prompt": prompt, **brief}).json()
    deck = wait_for(client, deck["id"], "draft")
    assert deck["status"] == "outline_ready", deck
    assert client.post(f"/api/decks/{deck['id']}/approve").status_code == 200
    deck = wait_for(client, deck["id"], "building")
    assert deck["status"] == "ready", deck
    return deck
