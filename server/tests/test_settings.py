"""Connections, routing presets and the provider clients (no network: httpx is stubbed)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from lectern.agents.contracts import OutlineDraft, schema_of
from lectern.llm import router
from lectern.llm.base import LLMError, LLMRequest
from lectern.llm.openai_compatible import OpenAICompatibleProvider

from .conftest import BOARD_PROMPT, wait_for

SECRET = "sk-test-secret-123"


def test_connections_never_return_keys(client: TestClient) -> None:
    listed = client.get("/api/settings/connections").json()
    by_id = {c["id"]: c for c in listed}
    assert {"offline", "anthropic", "openai", "openrouter", "ollama"} <= set(by_id)
    assert by_id["offline"]["status"] == "connected" and by_id["offline"]["kind"] == "offline"
    assert by_id["anthropic"] == {"id": "anthropic", "label": "Anthropic", "kind": "anthropic", "base_url": None,
                                  "has_key": False, "status": "not_configured", "detail": None}
    assert by_id["openai"]["kind"] == "openai_compatible" and by_id["openai"]["base_url"].startswith("https://")

    updated = client.put("/api/settings/connections",
                         json={"id": "openai", "api_key": SECRET, "base_url": "https://gateway.example/v1"})
    assert updated.status_code == 200 and SECRET not in updated.text
    openai = next(c for c in updated.json() if c["id"] == "openai")
    assert openai["has_key"] is True and openai["status"] == "configured"
    assert openai["base_url"] == "https://gateway.example/v1"
    assert SECRET not in client.get("/api/settings/connections").text
    assert SECRET not in client.get("/api/settings/routing").text

    cleared = client.put("/api/settings/connections", json={"id": "openai", "api_key": ""}).json()
    assert next(c for c in cleared if c["id"] == "openai")["has_key"] is False
    assert client.put("/api/settings/connections", json={"id": "nope", "api_key": "x"}).status_code == 404


def test_offline_connection_test_and_missing_key(client: TestClient) -> None:
    ok = client.post("/api/settings/connections/offline/test").json()
    assert ok["ok"] is True and ok["models"] == ["offline-1"]
    no_key = client.post("/api/settings/connections/anthropic/test").json()
    assert no_key["ok"] is False and "key" in no_key["detail"].lower()
    assert client.post("/api/settings/connections/nope/test").status_code == 404


def test_routing_defaults_presets_and_custom(client: TestClient) -> None:
    routing = client.get("/api/settings/routing").json()
    assert routing["preset"] == "balanced"
    assert set(routing["roles"]) == {"strategist", "writer", "art_director", "renderer", "critic", "editor"}
    assert all(r == {"provider": "offline", "model": "offline-1"} for r in routing["roles"].values())
    assert [p["label"] for p in routing["presets"]] == ["Best quality", "Balanced", "Lowest cost"]

    # With an Anthropic key, Balanced is the spec's default models.
    client.put("/api/settings/connections", json={"id": "anthropic", "api_key": SECRET})
    roles = client.get("/api/settings/routing").json()["roles"]
    for role in ("strategist", "writer", "art_director", "editor"):
        assert roles[role] == {"provider": "anthropic", "model": "claude-sonnet-5-5"}
    for role in ("renderer", "critic"):
        assert roles[role] == {"provider": "anthropic", "model": "claude-haiku-5-5"}
    assert client.get("/api/health").json()["provider"] == "anthropic"

    best = client.put("/api/settings/routing", json={"preset": "Best quality"}).json()
    assert best["preset"] == "best_quality" and best["roles"]["writer"]["model"] == "claude-opus-5-5"
    assert best["roles"]["critic"]["model"] == "claude-sonnet-5-5"
    cheap = client.put("/api/settings/routing", json={"preset": "lowest_cost"}).json()
    assert {r["model"] for r in cheap["roles"].values()} == {"claude-haiku-5-5"}

    custom = client.put("/api/settings/routing", json={
        "preset": "balanced", "roles": {"writer": {"provider": "offline", "model": "offline-1"}}}).json()
    assert custom["preset"] == "custom" and custom["roles"]["writer"]["provider"] == "offline"
    assert custom["roles"]["strategist"]["provider"] == "anthropic"
    assert client.put("/api/settings/routing", json={"preset": "turbo"}).status_code == 409
    assert client.put("/api/settings/routing",
                      json={"roles": {"writer": {"provider": "nope", "model": "x"}}}).status_code == 409

    # Removing the key falls back to offline at call time, so the product keeps working.
    client.put("/api/settings/connections", json={"id": "anthropic", "api_key": ""})
    assert client.get("/api/health").json()["provider"] == "offline"
    deck = client.post("/api/decks", json={"prompt": BOARD_PROMPT}).json()
    assert wait_for(client, deck["id"], "draft")["status"] == "outline_ready"


def _request() -> LLMRequest:
    return LLMRequest(role="strategist", task="outline", system="shared context", prompt="Plan the deck.",
                      schema=schema_of(OutlineDraft), tool_name="submit_outline")


def test_openai_compatible_uses_function_calling() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        arguments = json.dumps({"title": "Deck", "slides": [{"headline": "Revenue grew", "layout": "title"}]})
        return httpx.Response(200, json={
            "choices": [{"message": {"tool_calls": [{"function": {"name": "submit_outline",
                                                                  "arguments": arguments}}]}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 50}})

    provider = OpenAICompatibleProvider("openrouter", "https://openrouter.ai/api/v1/", SECRET,
                                        transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.complete(_request(), "some/model"))
    assert result.data["title"] == "Deck" and (result.input_tokens, result.output_tokens) == (900, 50)
    assert result.provider == "openrouter" and result.model == "some/model"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions" and seen["auth"] == f"Bearer {SECRET}"
    body = seen["body"]
    assert body["model"] == "some/model" and body["messages"][0] == {"role": "system", "content": "shared context"}
    assert body["tools"][0]["function"]["name"] == "submit_outline"
    assert body["tools"][0]["function"]["parameters"]["properties"]["slides"]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "submit_outline"}}
    OutlineDraft.model_validate(result.data)


def test_openai_compatible_errors_are_classified() -> None:
    def provider_for(status: int, payload: dict[str, Any]) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider("groq", "https://api.groq.com/openai/v1", SECRET,
                                        transport=httpx.MockTransport(lambda _r: httpx.Response(status, json=payload)))

    def error_of(status: int, payload: dict[str, Any]) -> LLMError:
        try:
            asyncio.run(provider_for(status, payload).complete(_request(), "m"))
        except LLMError as error:
            return error
        raise AssertionError("expected an error")

    assert error_of(429, {}).retryable and error_of(503, {}).retryable
    assert not error_of(401, {}).retryable and "key" in str(error_of(401, {})).lower()
    assert not error_of(400, {"error": {"message": "bad schema"}}).retryable
    assert error_of(200, {"choices": [{"message": {"content": "plain text"}}]}).retryable

    ok, detail, models = asyncio.run(OpenAICompatibleProvider(
        "ollama", "http://localhost:11434/v1", None,
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"data": [{"id": "llama3.1"}]}))).test())
    assert ok and models == ["llama3.1"] and "1 models" in detail


def test_router_rejects_answers_that_do_not_match_the_schema(data_dir: Any) -> None:
    from lectern.db import init_db
    from lectern.llm.base import LLMResult

    class Wrong:
        id = "wrong"
        calls = 0

        async def complete(self, request: LLMRequest, model: str) -> LLMResult:
            Wrong.calls += 1
            return LLMResult(data={"title": "x", "slides": [{"headline": "h", "layout": "not_a_layout"}]},
                             provider="wrong", model=model)

        async def test(self) -> tuple[bool, str, list[str] | None]:
            return True, "", None

    init_db()
    router.seed_defaults()
    router.set_provider_override(Wrong())
    try:
        asyncio.run(router.complete(_request(), OutlineDraft))
    except LLMError as error:
        assert "expected structure" in str(error)
    else:
        raise AssertionError("expected an error")
    assert Wrong.calls == 2          # asked once more with the validation error, then gave up


def test_anthropic_provider_builds_a_cached_tool_request() -> None:
    from lectern.llm.anthropic_provider import AnthropicProvider

    captured: dict[str, Any] = {}

    class Block:
        type = "tool_use"
        name = "submit_outline"
        input = {"title": "Deck", "slides": []}

    class Usage:
        input_tokens = 10
        output_tokens = 5
        cache_read_input_tokens = 700
        cache_creation_input_tokens = 0

    class Response:
        stop_reason = "tool_use"
        content = [Block()]
        usage = Usage()

    class Messages:
        async def create(self, **kwargs: Any) -> Response:
            captured.update(kwargs)
            return Response()

    provider = AnthropicProvider(api_key=SECRET)
    provider._client.messages = Messages()  # type: ignore[assignment]
    result = asyncio.run(provider.complete(_request(), "claude-sonnet-5-5"))
    assert result.data == {"title": "Deck", "slides": []} and result.input_tokens == 710
    assert captured["model"] == "claude-sonnet-5-5"
    assert captured["system"] == [{"type": "text", "text": "shared context",
                                   "cache_control": {"type": "ephemeral"}}]
    assert captured["tools"][0]["name"] == "submit_outline" and captured["tools"][0]["input_schema"]["properties"]
    assert captured["tool_choice"]["type"] == "auto"            # current models reject a forced tool choice
    assert "submit_outline" in captured["messages"][0]["content"]
