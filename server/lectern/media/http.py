"""Small async HTTP helpers shared by the key-based media providers. Tests patch `client_factory`."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx

from .base import MediaError

client_factory: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(timeout=120.0)  # noqa: E731
sleep: Callable[[float], Any] = asyncio.sleep


def _check(response: httpx.Response, who: str) -> httpx.Response:
    if response.status_code == 429 or response.status_code >= 500:
        raise MediaError(f"{who} is busy (HTTP {response.status_code}). Try again shortly.", retryable=True,
                         status=response.status_code)
    if response.status_code in (401, 403):
        raise MediaError(f"{who} rejected the API key.", status=response.status_code)
    if response.status_code >= 400:
        detail = response.text[:300]
        raise MediaError(f"{who} refused the request (HTTP {response.status_code}): {detail}",
                         status=response.status_code)
    return response


async def request(method: str, url: str, who: str, **kwargs: Any) -> httpx.Response:
    try:
        async with client_factory() as client:
            response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as error:
        raise MediaError(f"Could not reach {who}: {error}", retryable=True) from error
    return _check(response, who)


async def json(method: str, url: str, who: str, **kwargs: Any) -> Any:
    response = await request(method, url, who, **kwargs)
    try:
        return response.json()
    except ValueError as error:
        raise MediaError(f"{who} answered with something that is not JSON.") from error


async def download(url: str, who: str) -> tuple[bytes, str]:
    response = await request("GET", url, who, follow_redirects=True)
    return response.content, response.headers.get("content-type", "application/octet-stream").split(";")[0]


async def poll(fetch: Callable[[], Any], done: Callable[[Any], bool], failed: Callable[[Any], str | None],
               who: str, interval: float = 3.0, timeout: float = 600.0) -> Any:
    """Call `fetch` until `done(result)`; raise when `failed(result)` gives a reason or time runs out."""
    waited = 0.0
    while True:
        result = await fetch()
        reason = failed(result)
        if reason:
            raise MediaError(f"{who} could not finish: {reason}")
        if done(result):
            return result
        if waited >= timeout:
            raise MediaError(f"{who} did not finish in {int(timeout)} seconds.")
        await sleep(interval)
        waited += interval
