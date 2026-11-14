"""Smoke run against a running server: create, approve, build, render, critic, export, re-open.

    uv run uvicorn lectern.main:app --port 8000      # in one terminal
    uv run python scripts/smoke.py                   # in another
"""
from __future__ import annotations

import io
import sys
import time
from collections import Counter

import httpx
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api"
PROMPT = ("Our Q3 board review. Revenue is up 34%, but monthly logo churn went from 2.6% to 4.1%. "
          "I need the board to approve a $1.2M retention budget.")


def wait(client: httpx.Client, deck_id: str, leaving: str, timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        deck = client.get(f"/decks/{deck_id}").json()
        if deck["status"] != leaving:
            return deck
        time.sleep(0.3)
    raise SystemExit(f"timed out while the deck was {leaving}")


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        print("health:", client.get("/health").json())
        started = time.time()
        deck = client.post("/decks", json={"prompt": PROMPT}).json()
        deck = wait(client, deck["id"], "draft")
        print(f"outline: {deck['status']}, {len(deck['slides'])} slides, title \"{deck['title']}\"")
        client.post(f"/decks/{deck['id']}/approve").raise_for_status()
        deck = wait(client, deck["id"], "building")
        print(f"build: {deck['status']} in {time.time() - started:.1f}s, progress {deck['progress']}")
        for slide in deck["slides"]:
            print(f"  {slide['index']:>2} {slide['layout']:<13} score {slide.get('score')}  {slide['headline']}")
        rendered = client.get(f"/decks/{deck['id']}/render").json()
        print(f"render: {len(rendered)} slides, {sum(len(r['elements']) for r in rendered)} elements")
        critic = client.get(f"/decks/{deck['id']}/critic").json()
        print("critic:", {k: critic[k] for k in ("score", "story", "design", "editability")},
              f"{len([f for f in critic['findings'] if f['status'] == 'open'])} open findings")
        out = client.post(f"/decks/{deck['id']}/export", json={"format": "pptx", "include_notes": True}).json()
        print("export report:", {k: v for k, v in out["report"].items() if k != "checks"})
        for check in out["report"]["checks"]:
            print(f"  [{'ok' if check['ok'] else 'FAIL'}] {check['label']}: {check['detail']}")
        data = client.get(f"/files/{out['file_id']}").content
        print(f"file: {out['filename']} ({out['bytes']} bytes), file_id {out['file_id']}, deck {deck['id']}")
        prs = Presentation(io.BytesIO(data))
        kinds: Counter[str] = Counter()
        for page in prs.slides:
            for shape in page.shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    kinds["picture"] += 1
                elif shape.has_chart:
                    kinds["chart"] += 1
                elif shape.has_table:
                    kinds["table"] += 1
                elif shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
                    kinds["text box"] += 1
                else:
                    kinds["shape"] += 1
        notes = sum(1 for page in prs.slides if page.has_notes_slide)
        print(f"re-opened with python-pptx: {len(prs.slides)} slides, {dict(kinds)}, {notes} with notes, "
              f"size {prs.slide_width / 914400:.3f}in x {prs.slide_height / 914400:.3f}in")


if __name__ == "__main__":
    main()
