"""Unit tests for each lint rule (SPEC section 6) and the scores."""
from __future__ import annotations

from lectern.engine import lint
from lectern.engine.numbers import find_quantities
from lectern.engine.place import place
from lectern.engine.verbs import has_verb
from lectern.schema import (BulletsNode, ChartNode, Element, Item, ItemsNode, RenderedSlide, Series, Slide,
                            StatNode, Style, TextNode)

from . import samples


def rules_of(slide: Slide, user_rules: list[str] | None = None) -> set[str]:
    return {issue.rule for issue in lint.lint_slide(slide, rules=user_rules)}


def test_clean_samples_have_no_findings() -> None:
    for slide in samples.all_layouts():
        assert lint.lint_slide(slide) == [], slide.layout


def test_too_many_bullets_and_long_bullet() -> None:
    slide = samples.slide(1, "bullets", "Six points make the case", [BulletsNode(items=[
        "One", "Two", "Three", "Four", "Five",
        "This sixth bullet runs on for far too many words to be read at a glance by anyone in the room today"])])
    assert {"too_many_bullets", "long_bullet"} <= rules_of(slide)
    five = samples.slide(1, "bullets", "Five points make the case", [BulletsNode(items=["A b", "C d", "E", "F", "G"])])
    assert not {"too_many_bullets", "long_bullet"} & rules_of(five)


def test_long_headline() -> None:
    headline = "We are going to grow revenue by a third this year while also cutting churn in half"
    assert "long_headline" in rules_of(samples.slide(1, "bullets", headline, [BulletsNode(items=["A", "B"])]))
    assert lint.words(headline) > lint.MAX_HEADLINE_WORDS


def test_headline_not_claim() -> None:
    topic = samples.slide(2, "bullets", "Key metrics", [BulletsNode(items=["A", "B"])])
    claim = samples.slide(2, "bullets", "Churn rose to 4.1% in Q3", [BulletsNode(items=["A", "B"])])
    assert "headline_not_claim" in rules_of(topic)
    assert "headline_not_claim" not in rules_of(claim)
    # Title, agenda, section, closing and appendix slides may carry a plain title.
    assert "headline_not_claim" not in rules_of(samples.slide(1, "title", "Q3 board review", []))
    assert has_verb("Revenue is up 34%") and has_verb("Costs fall as volume grows")
    assert not has_verb("Market opportunity") and not has_verb("Our plan")


def test_missing_notes() -> None:
    slide = samples.slide(2, "bullets", "Churn rose in Q3", [BulletsNode(items=["A", "B"])], notes="  ")
    assert "missing_notes" in rules_of(slide)


def test_chart_rules() -> None:
    def chart(kind: str, categories: int, series: int) -> Slide:
        return samples.slide(3, "chart", "Churn rose in every segment", [ChartNode(
            kind=kind, categories=[f"C{i}" for i in range(categories)],  # type: ignore[arg-type]
            series=[Series(name=f"S{i}", values=[1.0] * categories) for i in range(series)])])

    assert "chart_too_many_series" in rules_of(chart("bar", 4, 6))
    assert "chart_too_many_series" not in rules_of(chart("bar", 4, 5))
    assert "chart_wrong_kind" in rules_of(chart("pie", 7, 1))
    assert "chart_wrong_kind" not in rules_of(chart("pie", 6, 1))
    assert "chart_wrong_kind" in rules_of(chart("line", 2, 1))
    assert "chart_wrong_kind" not in rules_of(chart("line", 3, 1))


def test_number_mismatch() -> None:
    def slide(notes: str) -> Slide:
        return samples.slide(4, "big_number", "Churn reached 4.1% in Q3",
                             [StatNode(value="4.1%", caption="Monthly logo churn")], notes=notes)

    drift = lint.lint_slide(slide("Churn is now 4.2%, the highest we have seen."))
    assert [i.rule for i in drift] == ["number_mismatch"] and drift[0].severity == "high"
    assert "4.2%" in drift[0].detail and "4.1%" in drift[0].detail
    assert "number_mismatch" not in rules_of(slide("Churn is 4.1%, up from 2.6% a quarter ago, across 3 segments."))
    money = samples.slide(5, "big_number", "We ask for a $1.2M budget", [StatNode(value="$1.2M")],
                          notes="The $1.3 million covers four hires.")
    assert "number_mismatch" in rules_of(money)
    assert [q.value for q in find_quantities("$1.2M and 34% in Q3 2026")] == [1_200_000.0, 34.0]


def test_empty_slot() -> None:
    slide = samples.slide(3, "chart", "Churn rose in Q3", [TextNode(role="body", value="No chart here.")])
    issues = [i for i in lint.lint_slide(slide) if i.rule == "empty_slot"]
    assert len(issues) == 1 and issues[0].severity == "high" and "chart" in issues[0].detail


def test_rule_violation() -> None:
    slide = samples.slide(2, "bullets", "Our synergy plan works", [BulletsNode(items=["We leverage scale", "B"])])
    assert "rule_violation" in rules_of(slide, ["Never say 'synergy'"])
    assert "rule_violation" in rules_of(slide, ["Avoid the word leverage"])
    assert "rule_violation" not in rules_of(slide, ["Always write in British English"])
    assert "rule_violation" not in rules_of(slide, ["Never say 'paradigm'"])
    assert lint.banned_terms("Don't use the words synergy, leverage or utilize") == ["synergy", "leverage", "utilize"]
    assert lint.banned_terms("Keep headlines short") == []


def test_text_overflow() -> None:
    slide = samples.slide(2, "three_column", "The plan has three parts", [ItemsNode(style="columns", items=[
        Item(title="Part", body=" ".join([samples.LONG] * 6)) for _ in range(3)])])
    assert "text_overflow" in rules_of(slide)
    assert "text_overflow" not in rules_of(samples.all_layouts()[6])


def _one_text(size: float, color: str, text: str = "Label") -> tuple[Slide, RenderedSlide]:
    slide = samples.slide(1, "bullets", "A claim is made here", [])
    element = Element(id="e1", node=None, kind="text", x=100, y=100, w=800, h=200, text=text,
                      style=Style(font_size=size, color=color))
    return slide, RenderedSlide(id="s1", index=1, background="#FFFFFF", elements=[element])


def test_min_font() -> None:
    assert lint.check_fonts(*_one_text(18, "#16181D"))            # a label under 20px
    assert not lint.check_fonts(*_one_text(20, "#16181D"))
    body = "This sentence is long enough to count as body text on a slide."
    assert lint.check_fonts(*_one_text(22, "#16181D", body))      # body under 24px
    assert not lint.check_fonts(*_one_text(24, "#16181D", body))
    for sample in samples.all_layouts():
        assert not lint.check_fonts(sample, place(sample))


def test_contrast() -> None:
    assert lint.check_contrast(*_one_text(30, "#BBBBBB"))
    assert not lint.check_contrast(*_one_text(30, "#16181D"))
    assert round(lint.contrast_ratio("#000000", "#FFFFFF")) == 21
    assert lint.contrast_ratio("#FFFFFF", "#2563EB") >= 4.5


def test_scores() -> None:
    issues = [lint.Issue("empty_slot", "high", "", ""), lint.Issue("long_headline", "medium", "", ""),
              lint.Issue("long_bullet", "low", "", "")]
    assert lint.slide_score(issues) == 100 - 15 - 8 - 3
    assert lint.slide_score(issues, lint.STORY_RULES) == 100 - 15 - 8
    assert lint.slide_score(issues, lint.DESIGN_RULES) == 100 - 3
    assert lint.slide_score([lint.Issue("empty_slot", "high", "", "")] * 10) == 0
    assert lint.mean([100, 77]) == 88 and lint.mean([]) == 100
    assert lint.STORY_RULES | lint.DESIGN_RULES == {
        "text_overflow", "min_font", "too_many_bullets", "long_bullet", "long_headline", "headline_not_claim",
        "missing_notes", "chart_too_many_series", "chart_wrong_kind", "number_mismatch", "empty_slot", "contrast",
        "rule_violation", "placeholder_text"}
