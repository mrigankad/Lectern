"""The Claude Code provider: subprocess arguments, parsing, the router retry, and the connection test (all mocked)."""
from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel

from lectern.llm import claude_code
from lectern.llm.base import LLMError, LLMRequest
from lectern.llm.claude_code import ClaudeCodeProvider

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}


def _request() -> LLMRequest:
    return LLMRequest(role="writer", task="t", system="REFERENCE CONTEXT", prompt="Write a title.", schema=SCHEMA)


def _envelope(**extra: Any) -> str:
    base = {"type": "result", "is_error": False, "result": "", "total_cost_usd": 0.01,
            "usage": {"input_tokens": 5, "cache_read_input_tokens": 10, "output_tokens": 7},
            "modelUsage": {"claude-sonnet-5-5": {}}}
    base.update(extra)
    return json.dumps(base)


class FakeRunner:
    def __init__(self, *outputs: str) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, args: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, stdin))
        return subprocess.CompletedProcess(args, 0, stdout=self.outputs.pop(0), stderr="")


def test_complete_uses_an_argument_list_stdin_and_no_tools() -> None:
    runner = FakeRunner(_envelope(structured_output={"title": "Churn doubled"}))
    provider = ClaudeCodeProvider(binary="claude", runner=runner)
    result = asyncio.run(provider.complete(_request(), "sonnet"))
    assert result.data == {"title": "Churn doubled"} and result.provider == "claude_code"
    assert result.model == "claude-sonnet-5-5" and result.input_tokens == 15 and result.output_tokens == 7
    args, stdin = runner.calls[0]
    assert isinstance(args, list) and args[:2] == ["claude", "-p"]
    assert args[args.index("--tools") + 1] == "" and "--strict-mcp-config" in args
    assert args[args.index("--model") + 1] == "sonnet"
    assert json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
    assert "REFERENCE CONTEXT" in stdin and "Write a title." in stdin


def test_complete_falls_back_to_json_in_the_result_text() -> None:
    runner = FakeRunner(_envelope(result='```json\n{"title": "From text"}\n```'))
    result = asyncio.run(ClaudeCodeProvider(binary="claude", runner=runner).complete(_request(), "sonnet"))
    assert result.data == {"title": "From text"}


def test_errors_are_classified() -> None:
    def error_of(stdout: str) -> LLMError:
        try:
            asyncio.run(ClaudeCodeProvider(binary="claude", runner=FakeRunner(stdout)).complete(_request(), "sonnet"))
        except LLMError as error:
            return error
        raise AssertionError("expected an error")

    assert error_of(_envelope(result="no json here")).retryable is True
    auth = error_of(_envelope(is_error=True, result="Not logged in · Please run /login", api_error_status=None))
    assert auth.status == 401 and auth.retryable is False
    assert error_of(_envelope(is_error=True, result="Overloaded", api_error_status=529)).retryable is True

    def timeout(args: list[str], stdin: str, t: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, t)
    try:
        asyncio.run(ClaudeCodeProvider(binary="claude", runner=timeout, timeout=1).complete(_request(), "sonnet"))
    except LLMError as error:
        assert error.retryable
    else:
        raise AssertionError("expected a timeout error")


def test_router_retries_once_on_an_invalid_answer(data_dir: Any) -> None:
    from lectern.llm import router

    class Out(BaseModel):
        title: str

    runner = FakeRunner(_envelope(structured_output={"name": "wrong"}),
                        _envelope(structured_output={"title": "Right"}))
    router.set_provider_override(ClaudeCodeProvider(binary="claude", runner=runner))
    from lectern import db
    db.reset_engine()
    out, _ = asyncio.run(router.complete(_request(), Out))
    assert out.title == "Right" and len(runner.calls) == 2
    assert "did not match" in runner.calls[1][1]


def test_connection_and_routing(client: TestClient, monkeypatch: Any) -> None:
    by_id = {c["id"]: c for c in client.get("/api/settings/connections").json()}
    assert by_id["claude_code"]["kind"] == "model" and by_id["claude_code"]["status"] == "not_configured"
    # Not usable until a test succeeds, so routing to it still falls back to offline.
    client.put("/api/settings/routing", json={"roles": {"writer": {"provider": "claude_code", "model": "sonnet"}}})
    assert client.get("/api/health").json()["provider"] == "offline"

    def fake(args: list[str], stdin: str, timeout: float) -> subprocess.CompletedProcess[str]:
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="2.1.325 (Claude Code)\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout=_envelope(structured_output={"ok": True}), stderr="")

    monkeypatch.setattr(claude_code, "_run", fake)
    monkeypatch.setattr(claude_code, "cli_path", lambda: "claude")
    tested = client.post("/api/settings/connections/claude_code/test").json()
    assert tested["ok"] is True and "2.1.325" in tested["detail"]
    assert client.get("/api/health").json()["provider"] == "claude_code"

    monkeypatch.setattr(claude_code, "cli_path", lambda: None)
    missing = client.post("/api/settings/connections/claude_code/test").json()
    assert missing["ok"] is False and "not found" in missing["detail"]
    assert client.get("/api/health").json()["provider"] == "offline"


def test_schema_is_cleaned_for_the_cli_strict_validator() -> None:
    from lectern.agents.contracts import SlideDraft, schema_of

    cleaned = json.dumps(claude_code.clean_schema(schema_of(SlideDraft)))
    assert '"discriminator"' not in cleaned
    kept = claude_code.clean_schema({"type": "object", "properties": {"discriminator": {"type": "string"}}})
    assert "discriminator" in kept["properties"]
