"""Retries with exponential backoff for provider calls."""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

from .base import LLMError

T = TypeVar("T")


async def with_retries(call: Callable[[], Awaitable[T]], *, attempts: int = 4, base_delay: float = 1.0,
                       max_delay: float = 20.0, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> T:
    """Run `call`, retrying retryable LLMErrors (429, 5xx, connection) with jittered backoff."""
    for attempt in range(attempts):
        try:
            return await call()
        except LLMError as error:
            if not error.retryable or attempt == attempts - 1:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            await sleep(delay * (0.5 + random.random() / 2))
    raise LLMError("The model provider did not answer.")  # unreachable; keeps type checkers satisfied
