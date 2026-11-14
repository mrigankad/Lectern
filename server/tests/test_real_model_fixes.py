"""Fixes found by running a real model (Claude Code) through the Q3 board deck."""
from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from lectern.llm.base import LLMRequest, LLMResult
from lectern.schema import StatNode
from lectern.sources import analyst, link

from .conftest import build_deck


def test_header_scale_and_derived_stats(monkeypatch: Any) -> None:
    cells = [["Month", "Revenue ($K)"], ["Apr", "2410"], ["Sep", "3230"]]
    table = analyst.table_of(cells)
    assert table["series"][0]["values"] == [2410000.0, 3230000.0] and table["series"][0]["name"] == "Revenue"
    assert analyst.scale_from_header("Logo churn (%)") == 1.0 and analyst.scale_from_header("ARR ($M)") == 1e6

    from lectern.sources import refs, service
    monkeypatch.setattr(service, "read_ref", lambda text, deck_id=None: (None, refs.parse_ref(text), [["3230"]]))
    growth = StatNode(value="34%", caption="Revenue growth", source="q3.xlsx!Revenue!B7")
    latest = StatNode(value="3,230", caption="Revenue in September", source="q3.xlsx!Revenue!B7")
    out = link.fill_linked([growth, latest])
    assert out[0].value == "34%" and out[0].source is None          # derived: not "3230%"
    assert out[1].value == "3230" and out[1].source == "q3.xlsx!Revenue!B7"


def test_a_deck_edit_can_remove_slides(client: TestClient) -> None:
    from lectern.llm import router

    deck = build_deck(client)
    first, *rest = deck["slides"]
    drop = [rest[0]["id"], rest[1]["id"], first["id"]]   # the title slide is never removed

    class Shorter:
        id = "stub"

        async def complete(self, request: LLMRequest, model: str) -> LLMResult:
            return LLMResult(data={"changes": [], "remove_slide_ids": drop, "summary": "Removed two slides."},
                             provider="stub", model="stub")

        async def test(self) -> tuple[bool, str, list[str] | None]:
            return True, "ok", None

    router.set_provider_override(Shorter())
    asked = client.post(f"/api/decks/{deck['id']}/ask", json={"scope": "deck", "message": "make it shorter"}).json()
    for _ in range(500):
        msg = next(m for m in client.get(f"/api/decks/{deck['id']}/messages").json() if m["id"] == asked["message_id"])
        if msg["status"] == "done":
            break
        time.sleep(0.02)
    after = client.get(f"/api/decks/{deck['id']}").json()
    assert len(after["slides"]) == len(deck["slides"]) - 2
    assert after["slides"][0]["id"] == first["id"]
    assert [s["index"] for s in after["slides"]] == list(range(1, len(after["slides"]) + 1))


def test_placeholder_text_is_a_finding() -> None:
    from lectern.engine import lint
    from lectern.schema import Slide

    slide = Slide.model_validate({"id": "s", "index": 1, "headline": "Three causes explain the churn",
                                  "layout": "three_column", "notes": "Add the [real] drivers before the meeting.",
                                  "nodes": [{"type": "items", "style": "columns", "items": [
                                      {"title": "Driver 1: [name the cause]"}, {"title": "Pricing"},
                                      {"title": "Onboarding"}]}]})
    issues = [i for i in lint.lint_slide(slide) if i.rule == "placeholder_text"]
    assert len(issues) == 1 and "[name the cause]" in issues[0].detail
    clean = slide.model_copy(update={"nodes": [slide.nodes[0].model_copy(update={"items": [
        slide.nodes[0].items[1], slide.nodes[0].items[2], slide.nodes[0].items[1]]})]})
    assert not [i for i in lint.lint_slide(clean) if i.rule == "placeholder_text"]


def test_an_edit_that_links_a_chart_gets_its_values(client: TestClient) -> None:
    """The Editor may return a chart with only a data_ref; it must not be dropped as empty."""
    from lectern.agents import apply
    from lectern.schema import ChartNode, Slide
    from .test_sources import upload, workbook

    deck = build_deck(client)
    upload(client, workbook(), "q3.xlsx", deck["id"])
    slide = Slide.model_validate(deck["slides"][1])
    chart = ChartNode(kind="line", categories=[], series=[], data_ref="q3.xlsx!Churn!A1:B4")
    out = apply.patched(slide, layout="chart", nodes=[chart])
    charts = [n for n in out.nodes if isinstance(n, ChartNode)]
    assert charts and charts[0].series and charts[0].categories


def test_step_labels_that_repeat_the_badge_are_not_drawn_twice() -> None:
    from lectern.engine.place import place
    from lectern.schema import Slide

    slide = Slide.model_validate({"id": "s", "index": 1, "headline": "The plan runs in three steps", "layout": "process",
                                  "notes": "n", "nodes": [{"type": "items", "style": "steps", "items": [
                                      {"title": "Diagnose", "label": "1"}, {"title": "Fund", "label": "Step 2"},
                                      {"title": "Act", "label": "Week 3"}]}]})
    texts = [e.text for e in place(slide).elements if getattr(e, "text", None)]
    assert texts.count("1") == 1 and "Step 2" not in texts and "Week 3" in texts


def test_a_target_is_not_a_mismatch_with_the_sheet() -> None:
    assert link._is_target("We aim to bring churn back under 3% by Q2.", "3%")
    assert link._is_target("The target of 3% holds.", "3%")
    assert not link._is_target("Churn was 3% in June.", "3%")


def test_large_chart_values_are_scaled_in_pptx() -> None:
    from lectern.export.pptx import _number_format

    assert _number_format("$", [2410000.0, 3230000.0]) == '"$"#,##0.00,,"M"'
    assert _number_format("%", [2.6, 4.1]) == '#,##0.0"%"'
    assert _number_format("", [120.0, 64.0]) == "#,##0"
