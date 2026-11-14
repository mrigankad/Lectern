"""Offline Strategist: pick a deck type from references/deck-types.md and turn its flow into an outline."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ... import knowledge
from .facts import Facts

DEFAULT_TYPE = "Business Review Deck"

_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "Business Review Deck": ("review", "qbr", "board", "quarterly", "results", "performance", "q1", "q2", "q3", "q4"),
    "Sales Deck": ("sales", "prospect", "proposal", "customer pitch", "demo", "buyer", "sell"),
    "Investor Pitch Deck": ("investor", "raise", "raising", "seed", "series a", "fundrais", "vc", "pitch deck",
                            "funding round"),
    "Training Deck": ("training", "onboarding", "teach", "workshop", "course", "learn", "how to", "lesson"),
    "Technical Architecture Deck": ("architecture", "system design", "migration", "infrastructure", "api",
                                    "technical", "platform design", "database"),
    "Case Study Deck": ("case study", "success story", "customer story"),
    "Strategy Review Deck": ("strategy", "strategic", "vision", "three-year", "long-term", "positioning"),
    "Project Status Deck": ("status", "status update", "project update", "sprint", "milestone", "steering", "progress update"),
    "All-Hands / Town Hall Deck": ("all-hands", "all hands", "town hall", "company update", "kickoff"),
}

# kind -> keywords found in a flow step name (first match wins, in this order)
_KIND_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("title", ("title",)),
    ("closing", ("closing", "contact", "thank", "q&a", "resources")),
    ("agenda", ("agenda", "learning objectives")),
    ("ask", ("resource needs", "the ask", "resources needed", "decision", "approval", "call to action",
             "resource implications", "budget status")),
    ("next", ("next steps", "upcoming priorities")),
    ("summary", ("executive summary", "summary", "key learnings")),
    ("timeline", ("milestone", "roadmap", "timeline")),
    ("process", ("how it works", "implementation", "go-to-market", "migration plan", "data flow", "practice",
                 "exercise")),
    ("options", ("options", "competitive", "comparison", "pricing", "packages", "technology stack",
                 "alternatives", "key decisions")),
    ("metrics", ("metrics", "traction", "results", "outcomes", "financial", "market opportunity",
                 "performance highlights")),
    ("wins", ("achievement", "wins", "accomplishment", "highlights", "people updates", "spotlight")),
    ("problem", ("problem", "challenge", "risk", "issues", "limitations", "current solutions", "mistakes")),
    ("diagram", ("architecture", "component", "security", "scalability")),
    ("team", ("team",)),
    ("proof", ("proof", "case study", "quote", "testimonial")),
    ("context", ("current state", "context", "overview", "why this matters", "current position", "requirements",
                 "objectives", "goals")),
    ("plan", ("solution", "plan", "recommend", "strategy", "approach", "pillars", "initiatives", "benefits",
              "priorities", "concept", "business model", "product")),
]

_SECTION = {"title": None, "agenda": None, "closing": None, "summary": "Summary", "context": "Where we stand",
            "metrics": "The numbers", "wins": "What is working", "problem": "The risk", "plan": "The plan",
            "process": "The plan", "timeline": "The plan", "options": "The options", "ask": "The decision",
            "next": "Next steps", "team": "The team", "diagram": "How it works", "proof": "The proof"}

# Order in which slides are dropped when the deck must be shorter than the type's flow.
_DROP_ORDER = ("agenda", "proof", "team", "diagram", "options", "timeline", "wins", "context", "process",
               "metrics", "summary", "plan", "problem", "next", "ask")
_EXTRA = ("summary", "timeline", "options", "closing", "context", "process")
_NUMBER_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}
_REPEATABLE = frozenset({"plan", "metrics", "context", "problem", "process", "wins", "options", "summary"})
_REPEAT_LAYOUTS = ("bullets", "process", "two_column", "timeline", "three_column", "table")


@dataclass
class Step:
    kind: str
    name: str          # the flow step name from deck-types.md
    headline: str = ""
    layout: str = "bullets"
    intent: str = ""
    section: str | None = None


def classify_deck(prompt: str) -> str:
    text = prompt.lower()
    types = knowledge.deck_types()
    best, best_score = DEFAULT_TYPE, 0
    for name, words in _TYPE_WORDS.items():
        score = sum(1 for word in words if word in text)
        if score > best_score and name in types:
            best, best_score = name, score
    return best if best in types else next(iter(types), DEFAULT_TYPE)


def step_kind(name: str) -> str:
    text = name.lower()
    for kind, words in _KIND_WORDS:
        if any(word in text for word in words):
            return kind
    return "plan"


def target_count(flow_length: int, slide_count: int | None, minutes: int | None, instruction: str | None,
                 current: int | None) -> int:
    count = slide_count or (round(minutes / 1.5) if minutes else min(flow_length, 10))
    base = current or count
    text = (instruction or "").lower()
    number = re.search(r"\b(\d{1,2})\s*(?:slides?|pages?)\b", text)
    if number:
        count = int(number.group(1))
    elif re.search(r"\b(shorter|short|fewer|tighter|cut|trim|condense|brief)\b", text):
        count = max(4, round(base * 0.7))
    elif re.search(r"\b(longer|more detail|more slides|expand|deeper)\b", text):
        count = base + 3
    return max(3, min(24, count))


def _clean_step(name: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", name).split("/")[0].strip()


def headline_for(step: Step, facts: Facts, count_hint: int = 3) -> str:
    """A claim for the slide, built from the prompt's facts where there are any."""
    kind = step.kind
    good, bad = facts.good, facts.bad
    n_word = _NUMBER_WORDS.get(count_hint, "Three")
    if kind == "title":
        return facts.topic
    if kind == "agenda":
        return "What we will cover"
    if kind == "closing":
        return "Thank you"
    if kind == "summary":
        if good and bad:
            return f"{good[0].sentence()}, but {_lower(bad[0].label)} needs a decision"
        if facts.metrics:
            return f"{facts.metrics[0].sentence()}, and here is what follows"
        return f"{n_word} points sum up {facts.topic_inline}"
    if kind == "context":
        if good and bad:
            moving = "rising" if bad[0].direction == "up" else "falling"
            return f"{good[0].label} is growing while {_lower(bad[0].label)} is {moving}"
        return f"Where {facts.topic_inline} stands today"
    if kind == "metrics":
        if len(facts.metrics) >= 2:
            word = _NUMBER_WORDS.get(min(len(facts.metrics), 4), "The")
            return f"{word} numbers tell the story of {facts.period or facts.topic_inline}"
        if facts.metrics:
            return facts.metrics[0].sentence()
        return f"The numbers behind {facts.topic_inline} need filling in"
    if kind == "wins":
        if good:
            return good[0].sentence()
        return f"What is working in {facts.topic_inline}"
    if kind == "problem":
        if bad:
            return bad[0].sentence()
        return f"What stands in the way of {facts.topic_inline}"
    if kind == "plan":
        if bad:
            return f"{n_word} moves bring {_lower(bad[0].label)} back under control"
        return f"{n_word} priorities move {facts.topic_inline} forward"
    if kind == "process":
        return "We deliver the plan in four steps"
    if kind == "timeline":
        return "The plan lands in four phases"
    if kind == "options":
        return "We compared three options and recommend one"
    if kind == "ask":
        return facts.ask_sentence() or facts.money_sentence() or "One decision moves this forward"
    if kind == "next":
        return f"{n_word} actions start this week"
    if kind == "team":
        return "The team that will deliver this"
    if kind == "diagram":
        return "How the pieces fit together"
    if kind == "proof":
        return "The evidence shows this works"
    return f"What you need to know about {_lower(_clean_step(step.name))}"


def layout_for(step: Step, facts: Facts, used: list[str]) -> str:
    kind = step.kind
    metrics = facts.metrics
    choices: dict[str, list[str]] = {
        "title": ["title"], "agenda": ["agenda"], "closing": ["closing"],
        "summary": ["summary"],
        "context": ["two_column"] if facts.good and facts.bad else ["bullets", "two_column"],
        "metrics": (["dashboard"] if len(metrics) >= 2 else ["big_number"] if metrics else ["bullets"]),
        "wins": ["big_number"] if facts.good else ["bullets", "three_column"],
        "problem": (["chart"] if facts.trend or len(_same_unit(facts)) >= 2 else ["big_idea", "bullets"]),
        "plan": ["three_column", "bullets"],
        "process": ["process"],
        "timeline": ["timeline"],
        "options": ["table"],
        "ask": ["big_number"] if facts.money else ["big_idea"],
        "next": ["next_steps"],
        "team": ["team"],
        "diagram": ["diagram"],
        "proof": ["big_idea", "case_study"],
    }
    options = choices.get(kind, ["bullets"])
    previous = used[-1] if used else None
    for layout in options:
        if layout != previous:
            return layout
    return options[0]


def _same_unit(facts: Facts) -> list:  # type: ignore[type-arg]
    by_unit: dict[str, list] = {}  # type: ignore[type-arg]
    for metric in facts.metrics:
        if metric.kind != "amount" and metric.unit:
            by_unit.setdefault(metric.unit, []).append(metric)
    return max(by_unit.values(), key=len, default=[])


def _intent(step: Step, facts: Facts) -> str:
    text = {
        "title": "Open the deck and say what it is about.",
        "agenda": "Tell the audience what is coming so they can follow.",
        "summary": "Give the whole argument in a few lines for anyone who reads only this slide.",
        "context": "Set out where things stand before the argument starts.",
        "metrics": "Show the few numbers that define the situation.",
        "wins": "Show what is working, with the number that proves it.",
        "problem": "Make the problem concrete with data.",
        "plan": "Lay out the plan in a small number of parts.",
        "process": "Show how the plan is carried out, step by step.",
        "timeline": "Show when each part of the plan happens.",
        "options": "Compare the options that were considered.",
        "ask": "State the decision or resources needed from the audience.",
        "next": "Say who does what next, and by when.",
        "team": "Introduce the people responsible.",
        "diagram": "Show how the parts of the system connect.",
        "proof": "Give evidence that this works.",
        "closing": "Close and invite questions.",
    }.get(step.kind, "Support the core message.")
    return f"{_clean_step(step.name)}: {text}"


def build_steps(facts: Facts, deck_type_name: str, slide_count: int | None, minutes: int | None,
                instruction: str | None = None, current_count: int | None = None) -> list[Step]:
    deck_type = knowledge.deck_types().get(deck_type_name)
    flow = list(deck_type.flow) if deck_type else ["Title", "Context", "Plan", "Next Steps"]
    steps = [Step(kind=step_kind(name), name=name) for name in flow]
    if not any(s.kind == "title" for s in steps):
        steps.insert(0, Step(kind="title", name="Title"))
    for kind in ("title", "agenda", "closing", "next", "ask", "summary", "team"):
        same = [i for i, s in enumerate(steps) if s.kind == kind]
        if not same:
            continue
        keep = same[0] if kind in {"title", "agenda"} else same[-1]
        steps = [s for i, s in enumerate(steps) if s.kind != kind or i == keep]   # one of each bookend
    target = target_count(len(steps), slide_count, minutes, instruction, current_count)

    # Shorten: drop the least essential kinds first, later duplicates before earlier ones.
    for kind in _DROP_ORDER:
        while len(steps) > target and any(s.kind == kind for s in steps):
            index = max(i for i, s in enumerate(steps) if s.kind == kind)
            steps.pop(index)
    # Lengthen: add kinds the flow lacks, before the closing slides.
    extras = [k for k in _EXTRA if not any(s.kind == k for s in steps)]
    while len(steps) < target:
        kind = extras.pop(0) if extras else "appendix"
        name = {"appendix": "Appendix"}.get(kind, kind.capitalize())
        step = Step(kind=kind, name=name)
        if kind in {"closing", "appendix"}:
            steps.append(step)
        else:
            tail = next((i for i, s in enumerate(steps) if s.kind in {"ask", "next", "closing"}), len(steps))
            steps.insert(tail, step)

    used: list[str] = []
    appendix_n = 0
    seen_kinds: set[str] = set()
    spare = [layout for layout in _REPEAT_LAYOUTS]
    for step in steps:
        if step.kind in seen_kinds and step.kind in _REPEATABLE:
            # The flow has several steps of one kind (two "plan" steps, say). Give the later ones their
            # own headline from the step name and a layout the deck has not used yet.
            name = _clean_step(step.name)
            step.layout = next((l for l in spare if l not in used), "bullets")
            verb = "work" if name.lower().endswith("s") else "works"
            step.headline = f"This is how our {name.lower()} {verb}"
            step.intent = _intent(step, facts)
            step.section = _SECTION.get(step.kind)
            step.kind = "plan"
            used.append(step.layout)
            continue
        seen_kinds.add(step.kind)
        if step.kind == "appendix":
            appendix_n += 1
            step.layout, step.section = "appendix", "Appendix"
            step.headline = f"Supporting detail {appendix_n}"
            step.intent = "Appendix: backup detail for questions."
        else:
            step.layout = layout_for(step, facts, used)
            step.headline = headline_for(step, facts)
            step.intent = _intent(step, facts)
            step.section = _SECTION.get(step.kind)
        used.append(step.layout)
    _ensure_variety(steps, facts)
    return steps


def _ensure_variety(steps: list[Step], facts: Facts) -> None:
    """When the prompt has numbers, the deck should show a chart and a big number somewhere."""
    layouts = [s.layout for s in steps]
    if not facts.metrics:
        return
    chartable = facts.trend or len(_same_unit(facts)) >= 2
    if chartable and "chart" not in layouts:
        target = next((s for s in steps if s.kind in {"problem", "metrics", "context", "wins"}
                       and s.layout not in {"big_number"}), None)
        if target:
            target.layout = "chart"
            metric = facts.trend or _same_unit(facts)[0]
            target.headline = metric.sentence()
    layouts = [s.layout for s in steps]
    if "big_number" not in layouts:
        target = next((s for s in steps if s.kind in {"ask", "wins", "metrics", "problem"}
                       and s.layout != "chart"), None)
        if target:
            target.layout = "big_number"
            if target.kind != "ask":
                metric = (facts.good or facts.metrics)[0]
                target.headline = metric.sentence()


def deck_title(facts: Facts) -> str:
    return facts.topic


def _lower(text: str) -> str:
    if len(text) > 1 and (text[1].isupper() or text[1].isdigit()):
        return text
    return text[:1].lower() + text[1:]
