"""Anthropic provider: structured output through tool use, prompt caching on the shared system context."""
from __future__ import annotations

from typing import Any

import anthropic

from .base import LLMError, LLMRequest, LLMResult


class AnthropicProvider:
    id = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        # Retries are handled by llm.retry so every provider backs off the same way.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url or None, max_retries=0)

    async def complete(self, request: LLMRequest, model: str) -> LLMResult:
        # Current Claude models reject a forced tool_choice, so the tool is offered with
        # tool_choice "auto" and the prompt says to call it; a reply without the call is retried.
        instruction = (f"{request.prompt}\n\nReturn your answer by calling the `{request.tool_name}` tool "
                       "exactly once. Do not answer in plain text.")
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                system=[{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
                tools=[{"name": request.tool_name, "description": request.tool_description,
                        "input_schema": request.schema}],
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                messages=[{"role": "user", "content": instruction}],
            )
        except anthropic.RateLimitError as error:
            raise LLMError("Anthropic is rate limiting requests. Trying again shortly.", retryable=True,
                           status=429) from error
        except anthropic.AuthenticationError as error:
            raise LLMError("Anthropic rejected the API key. Check it in Connections.", status=401) from error
        except anthropic.NotFoundError as error:
            raise LLMError(f"Anthropic does not know the model \"{model}\". Check model routing.",
                           status=404) from error
        except anthropic.APIStatusError as error:
            raise LLMError(f"Anthropic returned an error ({error.status_code}): {error.message}",
                           retryable=error.status_code >= 500, status=error.status_code) from error
        except anthropic.APIConnectionError as error:
            raise LLMError("Could not reach Anthropic. Check your network connection.", retryable=True) from error

        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model's answer was cut off before it finished.", retryable=True)
        data: dict[str, Any] | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == request.tool_name and isinstance(block.input, dict):
                data = block.input
                break
        if data is None:
            raise LLMError("The model answered in text instead of structured data.", retryable=True)
        usage = response.usage
        cached = (getattr(usage, "cache_read_input_tokens", 0) or 0) + \
                 (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        return LLMResult(data=data, provider=self.id, model=model,
                         input_tokens=(usage.input_tokens or 0) + cached, output_tokens=usage.output_tokens or 0)

    async def test(self) -> tuple[bool, str, list[str] | None]:
        try:
            page = await self._client.models.list(limit=50)
        except anthropic.AuthenticationError:
            return False, "Anthropic rejected the API key.", None
        except anthropic.APIStatusError as error:
            return False, f"Anthropic returned an error ({error.status_code}).", None
        except anthropic.APIConnectionError:
            return False, "Could not reach Anthropic. Check your network connection.", None
        models = [model.id for model in page.data]
        return True, f"Connected. {len(models)} models available.", models
