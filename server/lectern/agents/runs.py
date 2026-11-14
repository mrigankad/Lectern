"""Run rows: one per agent step, announced on the event bus with a plain-language summary."""
from __future__ import annotations

from ..db import session
from ..events import bus
from ..llm.base import LLMResult
from ..models import RunRow, SlideRow, now
from ..schema import Run

LOCAL_PROVIDER = "lectern"     # steps done by Lectern's own deterministic code


def _publish(row: RunRow) -> None:
    data = {"id": row.id, "role": row.role, "status": row.status, "summary": row.summary}
    if row.slide_index is not None:
        data["slide_index"] = row.slide_index
    bus.publish(row.deck_id, "run.updated", data)


def start(deck_id: str, role: str, summary: str, slide: SlideRow | None = None) -> RunRow:
    row = RunRow(deck_id=deck_id, role=role, summary=summary, status="running",
                 slide_id=slide.id if slide else None, slide_index=slide.position if slide else None)
    with session() as s:
        s.add(row)
        s.commit()
    _publish(row)
    return row


def finish(run: RunRow, summary: str, result: LLMResult | None = None, *, failed: bool = False,
           error: str | None = None, model: str = "") -> RunRow:
    with session() as s:
        row = s.get(RunRow, run.id) or run
        row.status = "failed" if failed else "done"
        row.summary = summary
        row.error = error
        row.ended_at = now()
        if result is not None:
            row.provider, row.model = result.provider, result.model
            row.input_tokens, row.output_tokens = result.input_tokens, result.output_tokens
        else:
            row.provider, row.model = LOCAL_PROVIDER, model
        s.add(row)
        s.commit()
    _publish(row)
    return row


def to_run(row: RunRow) -> Run:
    return Run(id=row.id, role=row.role, slide_index=row.slide_index, status=row.status, summary=row.summary,
               provider=row.provider, model=row.model, input_tokens=row.input_tokens,
               output_tokens=row.output_tokens, started_at=row.started_at, ended_at=row.ended_at)
