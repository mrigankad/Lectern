"""The offline provider writes a sensible, varied deck from the prompt alone, and never invents numbers."""
from __future__ import annotations

import pytest

from lectern import knowledge
from lectern.engine.lint import lint_slide
from lectern.engine.numbers import find_quantities
from lectern.layouts.adapt import missing_slots
from lectern.llm.offline import editor, outline
from lectern.llm.offline.facts import extract
from lectern.llm.offline.provider import OfflineProvider
from lectern.schema import Slide

from .conftest import BOARD_PROMPT
from .test_place import assert_invariants

PROMPTS = {
    "board": BOARD_PROMPT,
    "pitch": ("Create a pitch deck for Tidal, an AI scheduling tool for dental clinics. We have 120 clinics, "
              "ARR is $840K and grew 3x this year. We are raising a $4M seed round."),
    "training": "A training deck on how to run effective one-on-ones for new managers",
    "status": ("Project Atlas status update: migration is 70% complete, we slipped two weeks, "
               "budget is $250K of $400K spent."),
    "bare": "Something about our plans",
}


def generate(prompt: str, **brief: object) -> tuple[dict, list[Slide]]:
    provider = OfflineProvider()
    full = {"prompt": prompt, **brief}
    plan = provider._outline({"brief": full})
    entries = [{"index": i + 1, **entry} for i, entry in enumerate(plan["slides"])]
    slides = []
    for entry in entries:
        draft = provider._write_slide({"brief": full, "slide": entry, "outline": entries})
        slides.append(Slide.model_validate({"id": f"s{entry['index']}", "index": entry["index"],
                                            "section": entry["section"], "status": "ready", **draft}))
    return plan, slides


def test_reference_knowledge_is_loaded() -> None:
    assert len(knowledge.deck_types()) == 9 and len(knowledge.layout_patterns()) == 20
    review = knowledge.deck_types()["Business Review Deck"]
    assert review.flow[0] == "Title" and "Next Steps" in review.flow and review.slide_range == (10, 15)
    assert "Chart Selection Guide" in knowledge.reference_text()


def test_facts_from_the_board_prompt() -> None:
    facts = extract(BOARD_PROMPT)
    assert facts.topic == "Q3 board review" and facts.period == "Q3"
    assert facts.ask == "approve a $1.2M retention budget" and facts.audience == "the board"
    by_label = {m.label: m for m in facts.metrics}
    assert by_label["Revenue"].value == "34%" and by_label["Revenue"].good is True
    churn = by_label["Monthly logo churn"]
    assert (churn.before, churn.value, churn.good) == ("2.6%", "4.1%", False)
    assert by_label["Retention budget"].value == "$1.2M"


def test_deck_type_comes_from_the_prompt() -> None:
    assert outline.classify_deck(PROMPTS["board"]) == "Business Review Deck"
    assert outline.classify_deck(PROMPTS["pitch"]) == "Investor Pitch Deck"
    assert outline.classify_deck(PROMPTS["training"]) == "Training Deck"
    assert outline.classify_deck(PROMPTS["status"]) == "Project Status Deck"


def test_board_deck_is_varied_and_uses_the_numbers() -> None:
    plan, slides = generate(BOARD_PROMPT)
    assert plan["title"] == "Q3 board review" and plan["deck_type"] == "Business Review Deck"
    layouts = [s.layout for s in slides]
    assert layouts[0] == "title" and len(slides) == 10
    assert "chart" in layouts and "big_number" in layouts
    assert set(layouts) & {"three_column", "process", "two_column"}
    assert len(set(layouts)) >= 8
    assert all(a != b for a, b in zip(layouts, layouts[1:]))        # no layout twice in a row

    chart = next(n for s in slides for n in s.nodes if n.type == "chart")
    assert chart.categories == ["Q2", "Q3"] and chart.series[0].values == [2.6, 4.1] and chart.unit == "%"
    stats = [n.value for s in slides for n in s.nodes if n.type == "stat"]
    assert {"34%", "4.1%", "$1.2M"} <= set(stats)
    assert any("approve a $1.2M retention budget" in s.headline for s in slides)


@pytest.mark.parametrize("name", list(PROMPTS))
def test_generated_decks_are_clean_and_placeable(name: str) -> None:
    from lectern.engine.place import place_deck

    prompt = PROMPTS[name]
    _plan, slides = generate(prompt)
    assert 3 <= len(slides) <= 15
    allowed = {q.value for q in find_quantities(prompt)}
    for slide in slides:
        assert slide.notes.strip(), slide.layout
        assert not missing_slots(slide.layout, slide.nodes), (slide.layout, slide.headline)
        blocking = [i for i in lint_slide(slide) if i.severity == "high"]
        assert not blocking, (slide.layout, slide.headline, blocking)
        for node in slide.nodes:                                    # every figure shown as data is the user's
            if node.type == "stat":
                assert {q.value for q in find_quantities(node.value)} <= allowed, node.value
    for rendered in place_deck(slides):
        assert_invariants(rendered)


def test_slide_count_and_minutes_are_respected() -> None:
    assert len(generate(BOARD_PROMPT, slide_count=6)[1]) == 6
    assert len(generate(BOARD_PROMPT, slide_count=14)[1]) == 14
    assert len(generate(BOARD_PROMPT, minutes=9)[1]) == 6
    shorter = OfflineProvider()._outline({"brief": {"prompt": BOARD_PROMPT}, "instruction": "make it shorter",
                                          "current": {"slides": [{}] * 10}})
    assert len(shorter["slides"]) == 7


def test_offline_editor_understands_simple_requests() -> None:
    facts = extract(BOARD_PROMPT)
    _plan, slides = generate(BOARD_PROMPT)
    summary = next(s for s in slides if s.layout == "summary")
    changed, said = editor.edit_slide(summary, "add a bullet: churn is highest in SMB", facts)
    assert changed is not None and "Churn is highest in SMB" in changed.nodes[1].items and "Added" in said
    changed, _ = editor.edit_slide(summary, "remove the last bullet", facts)
    assert changed is not None and len(changed.nodes[1].items) == len(summary.nodes[1].items) - 1
    changed, _ = editor.edit_slide(summary, "use the three column layout", facts)
    assert changed is not None and changed.layout == "three_column" and changed.nodes[1].type == "items"
    changed, said = editor.edit_slide(summary, "turn this into a chart", facts)
    assert changed is not None and changed.layout == "chart" and any(n.type == "chart" for n in changed.nodes)
    unchanged, said = editor.edit_slide(summary, "make it pop", facts)
    assert unchanged is None and "offline" in said


def test_offline_chart_text_describes_only_the_charted_series() -> None:
    """QA: the offline writer put "Churn moved by 0.7 points" under a revenue chart."""
    provider = OfflineProvider()
    brief = {"prompt": "Churn went from 2.6% to 3.3%, and revenue rose from $1.2M to $1.6M this quarter."}
    entry = {"index": 2, "layout": "chart", "section": "Results", "intent": "metrics",
             "headline": "Revenue rose from $1.2M to $1.6M this quarter"}
    draft = provider._write_slide({"brief": brief, "slide": entry, "outline": [entry]})
    chart = next(n for n in draft["nodes"] if n["type"] == "chart")
    assert chart["series"][0]["name"].lower().startswith("revenue")
    body = " ".join(n["value"] for n in draft["nodes"] if n["type"] == "text" and n["role"] == "body")
    assert "churn" not in body.lower() and "revenue" in body.lower()
