"""Provider interface shared by the offline, Anthropic and OpenAI-compatible providers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMRequest:
    """One structured-output request from an agent.

    `system` is the shared, cacheable context (reference knowledge); `prompt` is the task.
    `schema` is the JSON schema the answer must match; providers return it through tool use.
    `payload` is the same task as structured data, which the offline provider works from.
    """
    role: str
    task: str
    system: str
    prompt: str
    schema: dict[str, Any]
    tool_name: str = "submit"
    tool_description: str = "Submit the result."
    payload: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 16000


@dataclass(frozen=True)
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(Exception):
    """A provider call failed. `retryable` is true for 429, 5xx and connection errors."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class Provider(Protocol):
    id: str

    async def complete(self, request: LLMRequest, model: str) -> LLMResult: ...

    async def test(self) -> tuple[bool, str, list[str] | None]: ...
