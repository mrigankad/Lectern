"""Offline Writer: fill a slide's nodes and notes from the prompt's facts.

It never invents figures. Numbers come from the prompt; where the prompt gives none, the slide
carries structure and plain wording the author can replace.
"""
from __future__ import annotations

import re
from typing import Any

from ...schema import (BulletsNode, ChartNode, Item, ItemsNode, Node, QuoteNode, Series, StatNode, TableNode,
                       TextNode)
from .facts import Facts, Metric, previous_period
from .outline import step_kind

_LAYOUT_KIND = {"title": "title", "agenda": "agenda", "closing": "closing", "summary": "summary",
                "next_steps": "next", "timeline": "timeline", "process": "process", "team": "team",
                "diagram": "diagram", "table": "options", "dashboard": "metrics", "chart": "problem",
                "quote": "proof", "case_study": "proof", "section": "section", "appendix": "appendix"}

# theme keyword -> (title, body) points for plan-like slides
_THEMES: list[tuple[tuple[str, ...], list[tuple[str, str]]]] = [
    (("churn", "retention", "renewal", "attrition"), [
        ("Find the accounts at risk", "Score every account on usage, support load and renewal date."),
        ("Fix the first 90 days", "Rebuild onboarding so new customers reach value sooner."),
        ("Give every account an owner", "Name a success manager for each account that drives renewals."),
        ("Measure churn every month", "Report churn to this group monthly, split by segment.")]),
    (("revenue", "sales", "pipeline", "growth", "arr", "bookings"), [
        ("Focus on the best-fit customers", "Put the team on the segment that buys fastest and stays longest."),
        ("Shorten the sales cycle", "Remove the steps that add time without adding confidence."),
        ("Expand existing accounts", "Grow the customers who already see value."),
        ("Track the pipeline weekly", "Review coverage and conversion on a fixed rhythm.")]),
    (("cost", "budget", "spend", "efficiency", "margin", "savings"), [
        ("Cut what does not pay back", "Stop the spend that has no measurable return."),
        ("Consolidate vendors and tools", "Fewer contracts, better terms, less overlap."),
        ("Protect what drives growth", "Keep investing where the return is proven."),
        ("Report spend against plan", "Show the variance every month.")]),
    (("hire", "hiring", "team", "talent", "people", "manager", "one-on-one"), [
        ("Set clear expectations", "Agree what good looks like before the work starts."),
        ("Make time for regular conversations", "Hold a fixed slot and protect it."),
        ("Give feedback early", "Say what you see while it can still change the outcome."),
        ("Follow up on what was agreed", "Close each conversation with owners and dates.")]),
    (("launch", "product", "feature", "release", "roadmap"), [
        ("Solve one problem well", "Ship the smallest version that fixes the customer's main problem."),
        ("Launch with a small group", "Learn from early users before the full release."),
        ("Measure adoption, not shipping", "Track who uses it and whether they come back."),
        ("Decide what comes next from data", "Let usage set the next priority.")]),
    (("security", "compliance", "risk", "migration", "architecture", "platform", "infrastructure"), [
        ("Map what exists today", "List the systems, the data and who depends on them."),
        ("Move in small, reversible steps", "Each step can be rolled back without downtime."),
        ("Test before every cutover", "Prove each stage works under real load."),
        ("Monitor after the change", "Watch errors and latency until the system is stable.")]),
]
_DEFAULT_POINTS = [
    ("Focus on what matters most", "Pick the few moves that change the outcome."),
    ("Give each part one owner", "One accountable person for each workstream."),
    ("Measure progress every month", "Agree the measure now and report it on a fixed rhythm."),
    ("Review and adjust", "Check results each quarter and move resources to what works."),
]


def kind_of(slide: dict[str, Any]) -> str:
    intent = str(slide.get("intent") or "")
    if ":" in intent:
        return step_kind(intent.split(":", 1)[0]) if intent.split(":", 1)[0].strip().lower() != "appendix" \
            else "appendix"
    layout = str(slide.get("layout") or "")
    if layout in _LAYOUT_KIND:
        return _LAYOUT_KIND[layout]
    return step_kind(str(slide.get("headline") or ""))


def theme_points(facts: Facts) -> list[tuple[str, str]]:
    text = f"{facts.prompt} {facts.ask or ''}".lower()
    best: list[tuple[str, str]] = _DEFAULT_POINTS
    best_score = 0
    for words, points in _THEMES:
        score = sum(text.count(word) for word in words)
        if score > best_score:
            best, best_score = points, score
    return best


def _metric_for(headline: str, facts: Facts, prefer: list[Metric] | None = None) -> Metric | None:
    """The metric the headline talks about, else the first preferred one."""
    for metric in facts.metrics:
        if metric.value and metric.value in headline:
            return metric
    for metric in facts.metrics:
        if metric.label.lower() in headline.lower():
            return metric
    pool = prefer or facts.metrics
    return pool[0] if pool else None


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _fact_bullets(facts: Facts, limit: int = 4) -> list[str]:
    bullets = [m.sentence() for m in facts.metrics if m.kind != "amount"]
    ask = facts.ask_sentence()
    if ask:
        bullets.append(ask)
    if len(bullets) < 2:
        bullets.extend(_cap(s) for s in facts.sentences if s not in bullets and len(s.split()) <= 16
                       and not re.search("deck|presentation|slides", s, re.IGNORECASE)
                       and s.lower().rstrip(".") != facts.topic.lower())
    if len(bullets) < 2:
        bullets.extend(title for title, _ in theme_points(facts))
    return bullets[:limit]


def _chart(facts: Facts, headline: str) -> ChartNode | None:
    metric = _metric_for(headline, facts)
    trend = metric if metric and metric.kind == "from_to" else facts.trend
    if trend and trend.quantity and trend.before_quantity:
        before, after = previous_period(facts.period)
        scale = _display_scale(trend)
        return ChartNode(kind="bar", categories=[before, after],
                         series=[Series(name=trend.label, values=[trend.before_quantity.value / scale,
                                                                 trend.quantity.value / scale])],
                         unit=trend.unit or None)
    by_unit: dict[str, list[Metric]] = {}
    for m in facts.metrics:
        if m.quantity and m.unit and m.kind != "amount":
            by_unit.setdefault(m.unit, []).append(m)
    group = max(by_unit.values(), key=len, default=[])
    if len(group) >= 2:
        return ChartNode(kind="bar", categories=[m.label for m in group[:6]],
                         series=[Series(name=facts.period or "Value",
                                        values=[m.quantity.value for m in group[:6] if m.quantity])],
                         unit=group[0].unit or None)
    return None


def _display_scale(metric: Metric) -> float:
    """Chart money in the unit it was written in ($1.2M charts as 1.2, not 1200000)."""
    text = metric.value.lower()
    for suffix, scale in (("b", 1e9), ("m", 1e6), ("k", 1e3)):
        if re.search(rf"\d\s?{suffix}\b", text):
            return scale
    return 1.0


def _stat(metric: Metric) -> StatNode:
    return StatNode(value=metric.value, caption=metric.caption(), source="Source: figures from the brief")


def _items(points: list[tuple[str, str]], style: str, count: int, labels: list[str] | None = None) -> ItemsNode:
    items = [Item(title=title, body=body or None, label=labels[i] if labels and i < len(labels) else None)
             for i, (title, body) in enumerate(points[:count])]
    return ItemsNode(style=style, items=items)  # type: ignore[arg-type]


def _next_actions(facts: Facts) -> list[Item]:
    who = _cap(re.sub(r"^the\s+", "", facts.audience)) if facts.audience != "the audience" else "Sponsor"
    first = Item(title=_cap(facts.ask), label=f"{who} · Today") if facts.ask else \
        Item(title="Agree the plan and its priorities", label=f"{who} · Today")
    return [first,
            Item(title="Name an owner for each part of the plan", label="Within 2 weeks"),
            Item(title="Report progress against the plan", label="Next review")]


def _points_for(kind: str, facts: Facts) -> list[tuple[str, str]]:
    if kind in {"plan", "process", "diagram"}:
        return theme_points(facts)
    if kind == "wins":
        return [(m.sentence(), "") for m in facts.good] + [("The core plan is on track", "")]
    if kind == "problem":
        return [(m.sentence(), "") for m in facts.bad] + [("The cause is known and can be fixed", ""),
                                                          ("Waiting makes the gap wider", "")]
    return [(b, "") for b in _fact_bullets(facts)]


def write_nodes(slide: dict[str, Any], facts: Facts, outline: list[dict[str, Any]]) -> list[Node]:
    """Nodes (without the headline node) for one slide, shaped for its layout."""
    layout = str(slide.get("layout") or "bullets")
    headline = str(slide.get("headline") or "")
    kind = kind_of(slide)
    points = _points_for(kind, facts)
    nodes: list[Node] = []

    if layout == "title":
        lines = [m.sentence() for m in facts.metrics if m.kind != "amount"][:2]
        if lines:
            joiner = ", but " if facts.good and facts.bad else ", and "
            nodes.append(TextNode(role="subhead", value=joiner.join([lines[0]] + [_lower(x) for x in lines[1:]])))
        elif facts.ask:
            nodes.append(TextNode(role="subhead", value=_cap(facts.ask)))
        if facts.audience != "the audience":
            nodes.append(TextNode(role="caption", value=f"Prepared for {_lower(facts.audience)}"))
    elif layout == "agenda":
        seen: list[str] = []
        for entry in outline:
            section = entry.get("section")
            if section and section not in seen and section != "Appendix":
                seen.append(section)
        if len(seen) < 3:
            seen = [str(e.get("headline")) for e in outline
                    if e.get("layout") not in {"title", "agenda", "closing", "appendix"}][:6]
        nodes.append(ItemsNode(style="steps", items=[Item(title=s) for s in seen[:7]]))
    elif layout == "section":
        if slide.get("intent"):
            nodes.append(TextNode(role="subhead", value=str(slide["intent"]).split(":", 1)[-1].strip()))
    elif layout == "closing":
        nodes.append(TextNode(role="subhead", value="Questions and discussion"))
        if facts.ask:
            nodes.append(TextNode(role="caption", value=f"The decision: {facts.ask}"))
    elif layout == "big_idea":
        support = None
        if kind == "ask" and facts.bad:
            support = f"{facts.bad[0].sentence()}. This is what it takes to turn that around"
        elif kind in {"summary", "wins", "metrics", "context", "proof"} or (kind == "problem" and facts.bad):
            support = next((m.sentence() for m in facts.metrics if m.value not in headline
                            and m.kind != "amount"), None)
        if support:
            nodes.append(TextNode(role="body", value=support.rstrip(".") + "."))
    elif layout == "big_number":
        prefer = (facts.money or facts.amounts) if kind == "ask" else facts.good if kind == "wins"             else facts.bad or facts.metrics
        metric = _metric_for(headline, facts, prefer)
        if metric:
            nodes.append(_stat(metric))
            if kind == "ask":
                funded = [title for title, _ in theme_points(facts)[:3]]
                nodes.append(TextNode(role="body", value="What it pays for"))
                nodes.append(BulletsNode(items=funded))
            else:
                others = [m.sentence() for m in facts.metrics if m is not metric and m.kind != "amount"][:2]
                nodes.append(BulletsNode(items=(others + [title for title, _ in points
                                                         if metric.value not in title])[:3]))
    elif layout == "chart":
        chart = _chart(facts, headline)
        if chart:
            nodes.append(chart)
            # Describe only what the chart shows: its one series, before and after. A chart of several
            # metrics gets no movement sentence (QA: "Churn moved by 0.7 points" under a revenue chart).
            if len(chart.series) == 1 and len(chart.series[0].values) == 2:
                series = chart.series[0]
                trend = next((m for m in facts.metrics if m.label == series.name), None)
                delta = abs(series.values[1] - series.values[0])
                unit = " points" if chart.unit == "%" else ""
                verdict = "" if trend is None or trend.good is None else (
                    "The trend is in our favour." if trend.good else "Left alone, the trend continues.")
                nodes.append(TextNode(role="body", value=f"{series.name} moved by {delta:.2g}{unit}. {verdict}".strip()))
            nodes.append(TextNode(role="caption", value="Source: figures from the brief"))
    elif layout == "dashboard":
        nodes.extend(_stat(m).model_copy(update={"source": None}) for m in facts.metrics[:4])
    elif layout == "table":
        ask = _cap(facts.ask) if facts.ask else "The recommended plan"
        nodes.append(TableNode(columns=["Option", "What it means", "Trade-off"], rows=[
            ["Do nothing", "Keep the current course", "The problem grows"],
            [f"Recommended: {ask}", "Act on the cause now", "Needs commitment up front"],
            ["A smaller step", "Fix one part first", "Slower, and the gap stays open longer"]]))
    elif layout == "quote":
        # No quote in the brief: say so honestly rather than leave template text on the slide.
        nodes.append(QuoteNode(text="We have no customer's words on this yet. Two short calls this month will "
                                    "give us one.", attribution="Open question for the team"))
    elif layout == "case_study":
        nodes.append(ItemsNode(style="columns", items=[
            Item(title="Challenge", body=(facts.bad[0].sentence() if facts.bad else "Not in the brief yet")),
            Item(title="Solution", body=theme_points(facts)[0][0]),
            Item(title="Results", body=(facts.good[0].sentence() if facts.good else "To be measured"))]))
        if facts.good:
            nodes.append(_stat(facts.good[0]).model_copy(update={"source": None}))
    elif layout == "two_column":
        if kind in {"context", "summary", "metrics", "wins", "problem"} and (facts.good or facts.bad):
            working = [m.sentence() for m in facts.good] or ["The core plan is on track"]
            attention = [m.sentence() for m in facts.bad] or ["No measure is off track yet"]
            if facts.ask:
                attention.append(f"Decision needed: {facts.ask}")
            nodes.append(ItemsNode(style="columns", items=[
                Item(title="What is working", body="\n".join(working[:3])),
                Item(title="What needs attention", body="\n".join(attention[:3]))]))
        else:
            nodes.append(ItemsNode(style="columns", items=[
                Item(title="Today", body="\n".join(b for b in _fact_bullets(facts, 3))),
                Item(title="What changes", body="\n".join(title for title, _ in theme_points(facts)[:3]))]))
    elif layout == "three_column":
        nodes.append(_items(points if kind in {"plan", "process", "diagram"} else theme_points(facts),
                            "columns", 3))
    elif layout == "process":
        nodes.append(_items(theme_points(facts), "steps", 4))
    elif layout == "diagram":
        nodes.append(_items(theme_points(facts), "steps", 4))
    elif layout == "timeline":
        nodes.append(_items([("Decision", "The plan and its budget are agreed."),
                             ("Start", theme_points(facts)[0][0] + "."),
                             ("First results", "Early measures show whether it is working."),
                             ("Review", "Results come back to this group.")],
                            "timeline", 4, ["Now", "First 30 days", "Within 90 days", "Next quarter"]))
    elif layout == "team":
        nodes.append(ItemsNode(style="columns", items=[
            Item(title="Executive sponsor", label="Accountable", body="Owns the outcome and removes blockers."),
            Item(title="Plan owner", label="Responsible", body="Runs the plan day to day."),
            Item(title="Data owner", label="Measures", body="Reports progress every month.")]))
    elif layout == "next_steps":
        nodes.append(ItemsNode(style="steps", items=_next_actions(facts)))
    elif layout == "summary":
        nodes.append(BulletsNode(items=_fact_bullets(facts, 4)))
    elif layout == "appendix":
        if facts.metrics:
            nodes.append(TableNode(columns=["Measure", "Value", "Note"], rows=[
                [m.label, m.value, (f"Was {m.before}" if m.before else m.kind.replace("_", " "))]
                for m in facts.metrics[:7]]))
        else:
            nodes.append(BulletsNode(items=[_cap(s) for s in facts.sentences[:4]] or ["Add supporting detail."]))
    else:  # bullets and anything unknown
        bullets = [f"{title}: {_lower(body)}" if body else title for title, body in points][:4]
        nodes.append(BulletsNode(items=bullets or _fact_bullets(facts)))
    return nodes


def write_notes(slide: dict[str, Any], facts: Facts) -> str:
    kind = kind_of(slide)
    headline = str(slide.get("headline") or "").rstrip(".")
    guide = {
        "title": "Open by saying why this meeting matters now, in one sentence.",
        "agenda": "Walk through the sections quickly; say how long the talk will take.",
        "summary": "If the audience remembers one slide, it should be this one. Say each line once, plainly.",
        "context": "Set out both sides fairly before moving to the problem.",
        "metrics": "Read out the numbers and say which one matters most.",
        "wins": "Give credit, then explain what caused the result.",
        "problem": "Let the data land before explaining it. Say what happens if nothing changes.",
        "plan": "Name each part, who owns it, and what it changes.",
        "process": "Take the steps in order and say what is done at the end of each.",
        "timeline": "Point to the first milestone and when the audience will hear back.",
        "options": "Explain why the alternatives were set aside.",
        "ask": "State the decision clearly, then stop and let the room respond.",
        "next": "Confirm the owners and dates before the meeting ends.",
        "team": "Say why these are the right people for this work.",
        "diagram": "Trace one example through the diagram from left to right.",
        "proof": "Tell the story behind the evidence in two sentences.",
        "closing": "Thank the audience and restate the decision you need.",
        "appendix": "Backup detail; show only if asked.",
        "section": "Pause here to mark the change of subject.",
    }.get(kind, "Explain why this matters to the audience.")
    lead = f"{headline}. " if headline and kind not in {"title", "agenda", "closing", "appendix", "section"} else ""
    return f"{lead}{guide}"


def _lower(text: str) -> str:
    if len(text) > 1 and (text[1].isupper() or text[1].isdigit()):
        return text
    return text[:1].lower() + text[1:]
