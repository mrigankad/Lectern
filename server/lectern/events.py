"""In-process pub/sub. Each SSE connection subscribes to one deck's channel."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

PING_SECONDS = 20.0
EventQueue = asyncio.Queue[tuple[str, dict[str, Any]]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[EventQueue]] = {}

    def publish(self, deck_id: str, event: str, data: dict[str, Any] | None = None) -> None:
        for queue in list(self._subscribers.get(deck_id, ())):
            queue.put_nowait((event, data or {}))

    def subscribe(self, deck_id: str) -> EventQueue:
        queue: EventQueue = asyncio.Queue()
        self._subscribers.setdefault(deck_id, set()).add(queue)
        return queue

    def unsubscribe(self, deck_id: str, queue: EventQueue) -> None:
        subscribers = self._subscribers.get(deck_id)
        if subscribers:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(deck_id, None)

    async def stream(self, deck_id: str, ping_seconds: float = PING_SECONDS) -> AsyncIterator[str]:
        """Yield SSE frames for a deck until the client disconnects."""
        queue = self.subscribe(deck_id)
        try:
            yield format_sse("ping", {})
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=ping_seconds)
                except asyncio.TimeoutError:
                    yield format_sse("ping", {})
                    continue
                yield format_sse(event, data)
        finally:
            self.unsubscribe(deck_id, queue)


def format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


bus = EventBus()
