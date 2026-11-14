"""Analyst: before the Strategist plans, read the deck's data sources and hand over the key numbers with
their cell or page references and chart suggestions (stored on the brief as `data_facts`)."""
from __future__ import annotations

from typing import Any

from .. import store
from ..sources import analyst as reader
from ..sources import service
from . import runs


def prepare(deck_id: str, brief: dict[str, Any]) -> dict[str, Any]:
    """Return the brief with `data_facts` filled from the deck's sources (unchanged when it has none)."""
    sources = service.list_sources(deck_id)
    ids = [s.id for s in sources if s.status == "ready"]
    if not ids:
        return brief
    run = runs.start(deck_id, "analyst", f"Analyst is reading {len(ids)} data source{'s' if len(ids) > 1 else ''}.")
    try:
        facts = reader.facts_for(ids)
    except Exception as error:  # noqa: BLE001  (the deck can still be written from the prompt)
        runs.finish(run, "Analyst could not read the data sources.", failed=True, error=str(error))
        return brief
    charts = sum(1 for f in facts if f.get("kind") == "chart")
    numbers = len(facts) - charts
    brief = {**brief, "data_facts": facts, "source_ids": ids}
    store.update_deck(deck_id, brief=brief)
    runs.finish(run, f"Analyst found {numbers} key number{'s' if numbers != 1 else ''} and "
                     f"{charts} chart{'s' if charts != 1 else ''} in the data, each with its cell reference.")
    return brief


def facts_block(brief: dict[str, Any]) -> str:
    """The Analyst's facts for an agent prompt."""
    facts = brief.get("data_facts") or []
    if not facts:
        return ""
    lines = ["Facts the Analyst read from the user's data sources. Use these exact figures, never round or "
             "change them, and cite the references once, in a last line of the speaker notes that starts "
             "\"Source:\", not in the sentences the speaker will say. To show a suggested chart, add a chart "
             "node whose data_ref is the reference given; Lectern fills its values from the cells."]
    for fact in facts:
        if fact.get("kind") == "chart":
            lines.append(f"- Chart: {fact.get('headline') or fact.get('label')} — {fact.get('chart')} chart, "
                         f"data_ref {fact['data_ref']}. {fact.get('reason', '')}")
        else:
            lines.append(f"- {reader.fact_sentence(fact)} [{fact.get('ref')}]")
    return "\n".join(lines)
