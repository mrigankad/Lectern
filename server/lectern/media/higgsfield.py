"""Higgsfield through its CLI (`higgsfield generate create ... --wait --json`), which bills real credits.

The CLI holds its own login (`higgsfield auth login`), so no key is stored here. The executable is run
directly (never through a shell) so a prompt cannot inject commands. Tests replace `run`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Awaitable, Callable

from .. import config
from . import http
from .base import Kind, MediaError, MediaResult, full_prompt, image_size, require_kind

Runner = Callable[[list[str], float], Awaitable[tuple[int, str, str]]]
IMAGE_ASPECTS = {"16:9", "4:3", "1:1", "3:4", "9:16"}


def image_model() -> str:
    return os.environ.get("LECTERN_HIGGSFIELD_IMAGE_MODEL", "gpt_image_2_5")


def video_model() -> str:
    return os.environ.get("LECTERN_HIGGSFIELD_VIDEO_MODEL", "seedance_2_0_mini")


async def _run(args: list[str], timeout: float) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        raise MediaError("Higgsfield did not finish in time.", retryable=False) from None
    return process.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


run: Runner = _run


def parse_json(text: str) -> Any:
    text = text.strip()
    for start in (0, *(m.start() for m in re.finditer(r"[\[{]", text))):
        try:
            return json.loads(text[start:])
        except ValueError:
            continue
    return None


def result_urls(data: Any) -> list[tuple[str, str | None]]:
    """(result_url, preview url) pairs from a CLI JSON answer of any nesting."""
    found: list[tuple[str, str | None]] = []
    if isinstance(data, dict):
        url = data.get("result_url") or data.get("url")
        if isinstance(url, str) and url.startswith("http"):
            found.append((url, data.get("min_result_url") if isinstance(data.get("min_result_url"), str) else None))
        else:
            for value in data.values():
                found.extend(result_urls(value))
    elif isinstance(data, list):
        for value in data:
            found.extend(result_urls(value))
    return found


def explain(out: str, err: str) -> str:
    text = f"{err}\n{out}"
    if "not_enough_credits" in text:
        return "Your Higgsfield account does not have enough credits for this generation."
    if re.search(r"unauthori[sz]ed|not logged in|login", text, re.I):
        return "The Higgsfield CLI is not signed in. Run `higgsfield auth login`."
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return f"Higgsfield failed: {line[:240]}" if line else "Higgsfield failed without a message."


class HiggsfieldProvider:
    id = "higgsfield"
    kinds: tuple[Kind, ...] = ("image", "video")

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or config.higgsfield_bin()

    def _need(self) -> str:
        if not self.binary:
            raise MediaError("The Higgsfield CLI is not installed. Install it with `npm i -g @higgsfield/cli`.")
        return self.binary

    def _params(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[str]:
        params = ["--prompt", full_prompt(prompt, style), "--aspect_ratio", aspect]
        if kind == "image" and image_model().startswith("gpt_image"):
            params += ["--quality", "low"]
        return params

    async def cost(self, prompt: str, kind: Kind, aspect: str, style: str) -> float | None:
        model = image_model() if kind == "image" else video_model()
        code, out, _err = await run([self._need(), "generate", "cost", model, *self._params(prompt, kind, aspect, style),
                                     "--json"], 60)
        data = parse_json(out) if code == 0 else None
        value = data.get("credits") if isinstance(data, dict) else None
        return float(value) if isinstance(value, (int, float)) else None

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        if aspect not in IMAGE_ASPECTS:
            aspect = "16:9"
        binary = self._need()
        model = image_model() if kind == "image" else video_model()
        cost = await self.cost(prompt, kind, aspect, style)
        timeout = "5m" if kind == "image" else "20m"
        code, out, err = await run([binary, "generate", "create", model, *self._params(prompt, kind, aspect, style),
                                    "--wait", "--wait-timeout", timeout, "--json"],
                                   400 if kind == "image" else 1300)
        if code != 0:
            raise MediaError(explain(out, err), retryable=False)
        urls = result_urls(parse_json(out))
        if not urls:
            urls = [(u, None) for u in re.findall(r"https?://\S+\.(?:png|jpe?g|webp|mp4|mov|webm)", out)]
        if not urls:
            raise MediaError("Higgsfield finished but returned no file.")
        results = []
        for url, preview in urls:
            data, mime = await http.download(url, "Higgsfield")
            poster = None
            if kind == "video" and preview:
                try:
                    poster, _ = await http.download(preview, "Higgsfield")
                except MediaError:
                    poster = None
            width, height = image_size(data) if kind == "image" else image_size(poster or b"")
            results.append(MediaResult(data=data, mime=mime if mime != "application/octet-stream" else
                                       ("video/mp4" if kind == "video" else "image/png"),
                                       kind=kind, width=width, height=height, poster=poster, cost_estimate=cost,
                                       meta={"model": model, "url": url}))
        return results

    async def test(self) -> tuple[bool, str]:
        if not self.binary:
            return False, "The Higgsfield CLI is not installed. Install it with `npm i -g @higgsfield/cli`."
        try:
            code, out, err = await run([self.binary, "account", "status", "--json"], 60)
        except (OSError, MediaError) as error:
            return False, f"Could not run the Higgsfield CLI: {error}"
        if code != 0:
            return False, explain(out, err)
        data = parse_json(out)
        credits = data.get("credits") if isinstance(data, dict) else None
        return True, (f"Signed in. {credits} credits available." if credits is not None else "Signed in.")
