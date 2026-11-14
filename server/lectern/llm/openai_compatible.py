"""One client for every OpenAI-compatible endpoint: OpenAI, OpenRouter, LiteLLM, Groq, DeepSeek,
Mistral, Ollama and Gemini's compatibility endpoint. Structured output through function calling."""
from __future__ import annotations

import json
from typing import Any

import httpx

from .base import LLMError, LLMRequest, LLMResult


class OpenAICompatibleProvider:
    def __init__(self, provider_id: str, base_url: str, api_key: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 180.0) -> None:
        self.id = provider_id
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=self._timeout,
                                 transport=self._transport)

    async def complete(self, request: LLMRequest, model: str) -> LLMResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": request.system},
                         {"role": "user", "content": request.prompt}],
            "tools": [{"type": "function", "function": {
                "name": request.tool_name, "description": request.tool_description,
                "parameters": request.schema}}],
            "tool_choice": {"type": "function", "function": {"name": request.tool_name}},
        }
        try:
            async with self._client() as client:
                response = await client.post("/chat/completions", json=body)
        except httpx.HTTPError as error:
            raise LLMError(f"Could not reach {self.id} at {self._base_url}.", retryable=True) from error
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMError(f"{self.id} is busy ({response.status_code}). Trying again shortly.", retryable=True,
                           status=response.status_code)
        if response.status_code in (401, 403):
            raise LLMError(f"{self.id} rejected the API key. Check it in Connections.",
                           status=response.status_code)
        if response.status_code >= 400:
            raise LLMError(f"{self.id} returned an error ({response.status_code}): {_error_text(response)}",
                           status=response.status_code)
        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMError(f"{self.id} sent a reply that could not be read.", retryable=True) from error
        data = _arguments(message, request.tool_name)
        if data is None:
            raise LLMError("The model answered in text instead of structured data.", retryable=True)
        usage = payload.get("usage") or {}
        return LLMResult(data=data, provider=self.id, model=model,
                         input_tokens=int(usage.get("prompt_tokens") or 0),
                         output_tokens=int(usage.get("completion_tokens") or 0))

    async def test(self) -> tuple[bool, str, list[str] | None]:
        try:
            async with self._client() as client:
                response = await client.get("/models", timeout=15.0)
        except httpx.HTTPError:
            return False, f"Could not reach {self._base_url}.", None
        if response.status_code in (401, 403):
            return False, "The API key was rejected.", None
        if response.status_code >= 400:
            return False, f"The endpoint returned an error ({response.status_code}).", None
        try:
            models = sorted(str(item["id"]) for item in response.json().get("data", []) if "id" in item)
        except (ValueError, AttributeError, TypeError):
            models = []
        return True, f"Connected. {len(models)} models available.", models or None


def _arguments(message: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        if function.get("name") == tool_name:
            try:
                parsed = json.loads(function.get("arguments") or "{}")
            except ValueError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def _error_text(response: httpx.Response) -> str:
    try:
        error = response.json().get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        return str(error or response.text[:200])
    except (ValueError, AttributeError):
        return response.text[:200]
