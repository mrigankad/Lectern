"""Pipeline behaviour: the send-back loop, provider failures, pause/resume, restart recovery, events."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from lectern.events import EventBus, format_sse
from lectern.llm import router
from lectern.llm.base import LLMError, LLMRequest, LLMResult
from lectern.llm.offline.provider import OfflineProvider
from lectern.llm.retry import with_retries

from .conftest import BOARD_PROMPT, build_deck, wait_for


class ScriptedProvider:
    """Wraps the offline provider and lets a test rewrite or fail individual answers."""
    id = "scripted"

    def __init__(self) -> None:
        self.inner = OfflineProvider()
        self.calls: list[LLMRequest] = []
        self.fail_task: str | None = None
        self.bad_first_draft_for: int | None = None
        self.gate: asyncio.Event | None = None

    async def complete(self, request: LLMRequest, model: str) -> LLMResult:
        self.calls.append(request)
        if self.gate is not None and request.task == "write_slide":
            await self.gate.wait()
        if self.fail_task == request.task:
            raise LLMError("The provider is down.", retryable=False)
        result = await self.inner.complete(request, model)
        data = dict(result.data)
        slide = request.payload.get("slide") or {}
        if (request.task == "write_slide" and not request.payload.get("findings")
                and slide.get("index") == self.bad_first_draft_for):
            data["headline"] = ("This first draft of the headline rambles on for far longer than any headline "
                                "should ever be allowed to")
            data["nodes"] = [{"type": "bullets", "items": [f"Point {n}" for n in range(1, 9)]}]
        return LLMResult(data=data, provider=self.id, model="scripted-1", input_tokens=120, output_tokens=40)

    async def test(self) -> tuple[bool, str, list[str] | None]:
        return True, "ok", None


def test_send_back_loop_runs_once_and_fixes_the_slide(client: TestClient) -> None:
    provider = ScriptedProvider()
    provider.bad_first_draft_for = 3
    router.set_provider_override(provider)
    deck = build_deck(client)
    slide = deck["slides"][2]
    assert slide["status"] == "ready"
    assert len(slide["headline"].split()) <= 12
    bullets = next((n for n in slide["nodes"] if n["type"] == "bullets"), None)
    assert bullets is None or len(bullets["items"]) <= 5

    runs = [r for r in client.get(f"/api/decks/{deck['id']}/runs").json() if r.get("slide_index") == 3]
    roles = [r["role"] for r in runs]
    assert roles.count("writer") == 2 and roles.count("critic") == 2       # one send-back, then a re-check
    sent_back = next(r for r in runs if r["role"] == "critic")
    assert "sent slide 3 back" in sent_back["summary"]
    assert any("revised slide 3" in r["summary"] for r in runs)
    revise = [c for c in provider.calls if c.task == "write_slide" and c.payload.get("findings")]
    assert len(revise) == 1
    assert {f["rule"] for f in revise[0].payload["findings"]} >= {"long_headline", "too_many_bullets"}
    writer_run = next(r for r in runs if r["role"] == "writer")
    assert writer_run["provider"] == "scripted" and writer_run["input_tokens"] == 120
    # Other slides were not sent back.
    others = [r for r in client.get(f"/api/decks/{deck['id']}/runs").json()
              if r["role"] == "writer" and r.get("slide_index") == 5]
    assert len(others) == 1


def test_user_rules_reach_every_agent_prompt(client: TestClient) -> None:
    provider = ScriptedProvider()
    router.set_provider_override(provider)
    client.post("/api/rules", json={"text": "Always write in British English"})
    build_deck(client)
    tasks = {call.task for call in provider.calls}
    assert {"outline", "write_slide", "choose_layout"} <= tasks
    for call in provider.calls:
        assert "Always write in British English" in call.prompt, call.task
        assert "Layouts you can use" in call.system and "Business Review Deck" in call.system
        assert call.schema.get("properties")


def test_provider_failure_marks_deck_failed_and_retry_recovers(client: TestClient) -> None:
    provider = ScriptedProvider()
    router.set_provider_override(provider)
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    deck = wait_for(client, deck["id"], "draft")
    provider.fail_task = "write_slide"
    client.post(f"/api/decks/{deck['id']}/approve")
    failed = wait_for(client, deck["id"], "building")
    assert failed["status"] == "failed" and "could not be built" in failed["error"]
    assert all(s["status"] == "queued" for s in failed["slides"])
    runs = client.get(f"/api/decks/{deck['id']}/runs").json()
    assert any(r["status"] == "failed" and "could not finish" in r["summary"] for r in runs)

    provider.fail_task = None
    assert client.post(f"/api/decks/{deck['id']}/approve").json()["status"] == "building"
    assert wait_for(client, deck["id"], "building")["status"] == "ready"


def test_outline_failure_is_reported(client: TestClient) -> None:
    provider = ScriptedProvider()
    provider.fail_task = "outline"
    router.set_provider_override(provider)
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    deck = wait_for(client, deck["id"], "draft")
    assert deck["status"] == "failed" and deck["error"]
    provider.fail_task = None
    client.post(f"/api/decks/{deck['id']}/outline/regenerate", json={})
    assert wait_for(client, deck["id"], "draft")["status"] == "outline_ready"


def test_pause_and_resume(client: TestClient) -> None:
    provider = ScriptedProvider()
    router.set_provider_override(provider)
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    deck = wait_for(client, deck["id"], "draft")
    provider.gate = asyncio.Event()                     # hold the writers so the build cannot finish
    client.post(f"/api/decks/{deck['id']}/approve")
    paused = client.post(f"/api/decks/{deck['id']}/pause")
    assert paused.status_code == 200 and paused.json()["paused"] is True
    client.portal.call(_set, provider.gate)             # release the in-flight writer calls
    time.sleep(0.3)
    held = client.get(f"/api/decks/{deck['id']}").json()
    assert held["status"] == "building" and held["paused"] is True
    assert held["progress"]["ready"] == 0               # nothing moves past its next step while paused
    # QA: in-flight slides kept reading "Writing". The slides whose writer finished are held and say so.
    in_flight = [s for s in held["slides"] if s["status"] != "queued"]
    assert in_flight and all(s["status"] == "writing" and s["paused"] for s in in_flight)
    assert not any(s["paused"] for s in held["slides"] if s["status"] == "queued")

    resumed = client.post(f"/api/decks/{deck['id']}/resume")
    assert resumed.status_code == 200 and resumed.json()["paused"] is False
    done = wait_for(client, deck["id"], "building")
    assert done["status"] == "ready" and done["paused"] is False
    assert all(s["status"] == "ready" and not s["paused"] for s in done["slides"])
    assert client.post(f"/api/decks/{deck['id']}/pause").status_code == 409


async def _set(event: asyncio.Event) -> None:
    event.set()


def test_restart_recovery_marks_interrupted_work(data_dir: Path) -> None:
    from lectern.db import session
    from lectern.main import create_app
    from lectern.models import MessageRow, RunRow, SlideRow

    with TestClient(create_app()) as client:
        deck = build_deck(client)
        deck_id = deck["id"]
    # Simulate a crash in the middle of a build.
    from lectern import store
    with session() as s:
        s.add(RunRow(deck_id=deck_id, role="writer", status="running", summary="Writer is writing slide 2."))
        s.add(MessageRow(deck_id=deck_id, role="assistant", status="pending", text="shorten it"))
        row = s.get(SlideRow, deck["slides"][1]["id"])
        assert row is not None
        row.status = "writing"
        s.add(row)
        s.commit()
    store.update_deck(deck_id, status="building")

    with TestClient(create_app()) as client:
        after = client.get(f"/api/decks/{deck_id}").json()
        assert after["status"] == "failed" and "interrupted" in after["error"]
        assert after["slides"][1]["status"] == "queued"
        runs = client.get(f"/api/decks/{deck_id}/runs").json()
        assert runs[-1]["status"] == "failed" and "interrupted" in runs[-1]["summary"]
        assert client.get(f"/api/decks/{deck_id}/messages").json()[-1]["status"] == "failed"
        # Retry builds only what was not finished.
        assert client.post(f"/api/decks/{deck_id}/resume").status_code == 200
        done = wait_for(client, deck_id, "building")
        assert done["status"] == "ready" and done["progress"]["ready"] == done["progress"]["total"]


def test_retries_back_off_then_succeed() -> None:
    attempts: list[int] = []
    waits: list[float] = []

    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise LLMError("busy", retryable=True, status=429)
        return "ok"

    async def no_sleep(seconds: float) -> None:
        waits.append(seconds)

    assert asyncio.run(with_retries(flaky, attempts=4, base_delay=1.0, sleep=no_sleep)) == "ok"
    assert len(attempts) == 3 and len(waits) == 2 and waits[1] > waits[0] * 0.99

    async def fatal() -> str:
        attempts.append(1)
        raise LLMError("bad key", retryable=False, status=401)

    attempts.clear()
    try:
        asyncio.run(with_retries(fatal, sleep=no_sleep))
    except LLMError as error:
        assert error.status == 401
    assert len(attempts) == 1


def test_event_bus_delivers_to_deck_subscribers_only() -> None:
    async def scenario() -> list[tuple[str, dict[str, Any]]]:
        bus = EventBus()
        mine, other = bus.subscribe("a"), bus.subscribe("b")
        bus.publish("a", "slide.updated", {"slide_id": "s1", "index": 1, "status": "writing"})
        bus.publish("a", "outline.ready")
        got = [await mine.get(), await mine.get()]
        assert other.empty()
        bus.unsubscribe("a", mine)
        bus.publish("a", "ping")
        assert mine.empty()
        return got

    events = asyncio.run(scenario())
    assert events[0][0] == "slide.updated" and events[1] == ("outline.ready", {})
    assert format_sse("run.updated", {"id": "r1"}) == 'event: run.updated\ndata: {"id": "r1"}\n\n'


def test_events_are_published_during_a_build(client: TestClient) -> None:
    from lectern.events import bus

    seen: list[tuple[str, dict[str, Any]]] = []
    original = bus.publish

    def record(deck_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        seen.append((event, data or {}))
        original(deck_id, event, data)

    bus.publish = record  # type: ignore[method-assign]
    try:
        deck = build_deck(client)
    finally:
        bus.publish = original  # type: ignore[method-assign]
    names = {name for name, _ in seen}
    assert {"deck.updated", "outline.ready", "slide.updated", "run.updated"} <= names
    statuses = {data["status"] for name, data in seen if name == "slide.updated"}
    assert {"writing", "rendering", "checking", "ready"} <= statuses
    for name, data in seen:
        if name == "run.updated":
            assert set(data) >= {"id", "role", "status", "summary"} and data["summary"]
        if name == "deck.updated":
            assert set(data) >= {"status", "progress"} and set(data["progress"]) == {"ready", "total"}
    last = [data for name, data in seen if name == "deck.updated"][-1]
    assert last["status"] == "ready" and last["progress"]["ready"] == len(deck["slides"])


class TemplateTextProvider(ScriptedProvider):
    """Writes instruction-style template text on slide 3, first draft and revision alike."""

    async def complete(self, request: LLMRequest, model: str) -> LLMResult:
        result = await super().complete(request, model)
        if request.task == "write_slide" and (request.payload.get("slide") or {}).get("index") == 3:
            data = dict(result.data)
            data["nodes"] = [{"type": "items", "style": "columns", "items": [
                {"title": f"Area {n}: name the segment", "body": "Add the segment, its share of lost logos"}
                for n in (1, 2, 3)]}]
            return LLMResult(data=data, provider=self.id, model="scripted-1", input_tokens=1, output_tokens=1)
        return result


def test_template_text_blocks_ready_until_fixed_or_kept(client: TestClient) -> None:
    """Real-model run: a slide read "Area N: name the segment / Add the segment, its share of lost logos"."""
    from lectern.engine.lint import check_placeholders
    from lectern.schema import Slide

    for text in ("Area 1: name the segment", "Add the segment, its share of lost logos", "Insert chart here",
                 "Describe your solution"):
        slide = Slide.model_validate({"id": "s", "index": 2, "headline": "Churn comes from three areas",
                                      "layout": "bullets", "nodes": [{"type": "bullets", "items": [text]}]})
        assert check_placeholders(slide), text
    fine = Slide.model_validate({"id": "s", "index": 2, "headline": "We add two support hires",
                                 "layout": "bullets", "nodes": [{"type": "bullets", "items": [
                                     "Add the two support hires in October", "We name the owner today"]}]})
    assert not check_placeholders(fine)

    router.set_provider_override(TemplateTextProvider())
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    wait_for(client, deck["id"], "draft")
    client.post(f"/api/decks/{deck['id']}/approve")
    deck = wait_for(client, deck["id"], "building")
    held = deck["slides"][2]
    assert held["status"] == "sent_back"                    # not "ready" with template text on it
    assert all(s["status"] == "ready" for i, s in enumerate(deck["slides"]) if i != 2)
    finding = next(f for f in client.get(f"/api/decks/{deck['id']}/critic").json()["findings"]
                   if f["slide_id"] == held["id"] and f["rule"] == "placeholder_text")
    # Kept on purpose: the slide is released.
    client.post(f"/api/decks/{deck['id']}/critic/findings/{finding['id']}", json={"action": "keep"})
    assert client.get(f"/api/decks/{deck['id']}").json()["slides"][2]["status"] == "ready"
