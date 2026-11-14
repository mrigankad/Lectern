"""Claude Code provider: runs the locally installed, logged-in `claude` CLI non-interactively.

No API key is handled here; the CLI uses its own login. Each call is one `claude -p` subprocess with
built-in tools disabled, MCP servers and local settings skipped, and no session saved. Structured output
comes from `--json-schema` (the CLI validates it and returns `structured_output`); the router validates it
again against the agent's pydantic model and retries once when it does not match.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Callable

from .base import LLMError, LLMRequest, LLMResult

log = logging.getLogger("lectern.claude_code")
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT = 300.0
SYSTEM = ("You are one agent in Lectern, a presentation tool. Follow the context and task exactly and "
          "return only the requested structured result.")

Runner = Callable[[list[str], str, float], "subprocess.CompletedProcess[str]"]


def cli_path() -> str | None:
    return os.environ.get("LECTERN_CLAUDE_BIN") or shutil.which("claude")


def _run(args: list[str], stdin: str, timeout: float) -> "subprocess.CompletedProcess[str]":
    # An argument list, never a shell string. The prompt goes in on stdin.
    return subprocess.run(args, input=stdin, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, check=False)


def build_args(binary: str, model: str, schema: dict[str, Any] | None, system: str | None) -> list[str]:
    args = [binary, "-p", "--output-format", "json", "--model", model or DEFAULT_MODEL,
            "--tools", "",                      # no built-in tools: no Bash, no file access, no web
            "--strict-mcp-config",              # no MCP servers from the user's config
            "--setting-sources", "",            # ignore user/project/local settings and hooks
            "--no-session-persistence"]
    if schema is not None:
        args += ["--json-schema", json.dumps(clean_schema(schema), separators=(",", ":"))]
    if system:
        args += ["--system-prompt", system]
    return args


# OpenAPI keywords pydantic emits that the CLI's strict JSON Schema validator rejects.
_NON_STANDARD = {"discriminator"}


def clean_schema(node: Any, *, in_properties: bool = False) -> Any:
    """Drop non-standard keywords (not property names) so `--json-schema` accepts the schema."""
    if isinstance(node, dict):
        return {key: clean_schema(value, in_properties=key in ("properties", "$defs", "definitions")
                                  and not in_properties)
                for key, value in node.items() if in_properties or key not in _NON_STANDARD}
    if isinstance(node, list):
        return [clean_schema(item) for item in node]
    return node


class ClaudeCodeProvider:
    id = "claude_code"

    def __init__(self, binary: str | None = None, runner: Runner | None = None,
                 timeout: float = DEFAULT_TIMEOUT) -> None:
        self._binary = binary
        self._runner = runner or _run
        self._timeout = timeout
        self.calls = 0
        self.cost_usd = 0.0

    def _bin(self) -> str:
        binary = self._binary or cli_path()
        if not binary:
            raise LLMError("The Claude Code CLI ('claude') was not found. Install it and run `claude` once to log in.")
        return binary

    async def _invoke(self, args: list[str], stdin: str, timeout: float) -> dict[str, Any]:
        try:
            proc = await asyncio.to_thread(self._runner, args, stdin, timeout)
        except subprocess.TimeoutExpired as error:
            raise LLMError(f"Claude Code did not answer within {int(timeout)} seconds.", retryable=True) from error
        except OSError as error:
            raise LLMError(f"Could not start the Claude Code CLI: {error}.") from error
        self.calls += 1
        try:
            envelope = json.loads(proc.stdout or "")
        except ValueError:
            envelope = None
        if not isinstance(envelope, dict):
            text = (proc.stderr or proc.stdout or "").strip()[:300]
            if "login" in text.lower() or "auth" in text.lower():
                raise LLMError("Claude Code is not logged in. Run `claude` in a terminal and log in.", status=401)
            # "Error: --flag ..." is the CLI rejecting its arguments: retrying cannot help.
            raise LLMError(f"Claude Code sent a reply that could not be read ({proc.returncode}): {text}",
                           retryable=not text.startswith("Error: --"))
        if envelope.get("is_error"):
            message = str(envelope.get("result") or envelope.get("subtype") or "unknown error")[:300]
            status = envelope.get("api_error_status")
            auth = status in (401, 403) or "login" in message.lower() or "authenticat" in message.lower()
            if auth:
                raise LLMError("Claude Code is not logged in. Run `claude` in a terminal and log in.", status=401)
            raise LLMError(f"Claude Code returned an error: {message}",
                           retryable=status in (429, 500, 502, 503, 529) or "overloaded" in message.lower(),
                           status=status if isinstance(status, int) else None)
        return envelope

    async def complete(self, request: LLMRequest, model: str) -> LLMResult:
        # The shared context goes on stdin with the task: Windows caps a command line at 32k characters.
        args = build_args(self._bin(), model, request.schema, SYSTEM)
        prompt = (f"<context>\n{request.system}\n</context>\n\n{request.prompt}\n\nAnswer only with the structured result ({request.tool_description}). "
                  "Do not use any tools and do not add commentary.")
        envelope = await self._invoke(args, prompt, self._timeout)
        data = envelope.get("structured_output")
        if not isinstance(data, dict):
            data = _parse_json(envelope.get("result"))
        if data is None:
            raise LLMError("The model answered in text instead of structured data.", retryable=True)
        usage = envelope.get("usage") or {}
        cost = float(envelope.get("total_cost_usd") or 0.0)
        self.cost_usd += cost
        log.warning("claude_code call role=%s task=%s model=%s seconds=%.1f in=%s out=%s cost_usd=%.4f",
                    request.role, request.task, model, float(envelope.get("duration_ms") or 0) / 1000,
                    usage.get("input_tokens"), usage.get("output_tokens"), cost)
        used = next(iter(envelope.get("modelUsage") or {}), None) or model
        return LLMResult(data=data, provider=self.id, model=str(used),
                         input_tokens=int(usage.get("input_tokens") or 0)
                         + int(usage.get("cache_read_input_tokens") or 0)
                         + int(usage.get("cache_creation_input_tokens") or 0),
                         output_tokens=int(usage.get("output_tokens") or 0))

    async def test(self) -> tuple[bool, str, list[str] | None]:
        binary = cli_path() if self._binary is None else self._binary
        if not binary:
            return False, "The Claude Code CLI ('claude') was not found on this computer.", None
        try:
            version = await asyncio.to_thread(self._runner, [binary, "--version"], "", 30.0)
        except (OSError, subprocess.TimeoutExpired):
            return False, "The Claude Code CLI did not start.", None
        if version.returncode != 0:
            return False, "The Claude Code CLI did not start.", None
        label = (version.stdout or "").strip().splitlines()[0] if (version.stdout or "").strip() else "claude"
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        try:
            envelope = await self._invoke(build_args(binary, "haiku", schema, None), "Reply with ok=true.", 60.0)
        except LLMError as error:
            return False, f"{label}: {error}", None
        if not (isinstance(envelope.get("structured_output"), dict) or _parse_json(envelope.get("result"))):
            return False, f"{label}: the login probe did not return structured data.", None
        return True, f"Connected ({label}, using your Claude Code login).", ["sonnet", "opus", "haiku"]


def _parse_json(text: Any) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{"):] if "{" in cleaned else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None
