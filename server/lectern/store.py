"""Reads and writes that several routers and agents share: decks, slides, versions, findings, rules."""
from __future__ import annotations

from typing import Any

from sqlmodel import delete, select

from .db import session
from .engine import lint
from .engine.place import context_for
from .events import bus
from .layouts.adapt import ensure_headline
from .models import (DeckRow, FindingRow, MessageRow, RuleRow, RunRow, SlideRow, SlideVersionRow, new_id, now)
from .schema import Brief, Deck, DeckSummary, Finding, Progress, Slide, Theme

CRITIC_RULE_PREFIX = "critic:"


class NotFound(Exception):
    """The thing asked for does not exist (HTTP 404)."""


class Conflict(Exception):
    """The request cannot be done in the current state (HTTP 409)."""


# ---------------------------------------------------------------- conversions
# Slides whose build step is waiting for a paused deck to resume (filled by the pipeline, in memory:
# after a restart nothing is running, so nothing is held).
HELD: set[str] = set()


def to_slide(row: SlideRow) -> Slide:
    data: dict[str, Any] = {
        "id": row.id, "index": row.position, "section": row.section, "headline": row.headline,
        "layout": row.layout, "nodes": row.nodes or [], "notes": row.notes or "", "status": row.status,
        "score": row.score, "intent": row.intent, "paused": row.id in HELD,
    }
    slide = Slide.model_validate(data)
    return slide.model_copy(update={"nodes": ensure_headline(slide.nodes, slide.headline)})


def slide_rows(deck_id: str) -> list[SlideRow]:
    with session() as s:
        return list(s.exec(select(SlideRow).where(SlideRow.deck_id == deck_id).order_by(SlideRow.position)).all())


def get_deck_row(deck_id: str) -> DeckRow:
    with session() as s:
        row = s.get(DeckRow, deck_id)
    if row is None:
        raise NotFound("That deck does not exist. It may have been deleted.")
    return row


def get_slide_row(deck_id: str, slide_id: str) -> SlideRow:
    with session() as s:
        row = s.get(SlideRow, slide_id)
    if row is None or row.deck_id != deck_id:
        raise NotFound("That slide does not exist in this deck.")
    return row


def progress_of(rows: list[SlideRow]) -> Progress:
    return Progress(ready=sum(1 for r in rows if r.status == "ready"), total=len(rows))


def load_deck(deck_id: str) -> Deck:
    row = get_deck_row(deck_id)
    rows = slide_rows(deck_id)
    return Deck(id=row.id, title=row.title, status=row.status,  # type: ignore[arg-type]
                brief=Brief.model_validate(row.brief or {"prompt": ""}),
                theme=Theme.model_validate(row.theme or {}), slides=[to_slide(r) for r in rows],
                created_at=row.created_at, updated_at=row.updated_at, paused=row.paused,
                progress=progress_of(rows), error=row.error,
                icon=row.icon, icon_color=row.icon_color)


def list_decks() -> list[DeckSummary]:
    with session() as s:
        decks = s.exec(select(DeckRow).order_by(DeckRow.updated_at.desc())).all()  # type: ignore[attr-defined]
        slides = s.exec(select(SlideRow.deck_id, SlideRow.status)).all()
    by_deck: dict[str, list[str]] = {}
    for deck_id, status in slides:
        by_deck.setdefault(deck_id, []).append(status)
    return [DeckSummary(id=d.id, title=d.title, status=d.status,  # type: ignore[arg-type]
                        slide_count=len(by_deck.get(d.id, [])), updated_at=d.updated_at,
                        progress=Progress(ready=sum(1 for st in by_deck.get(d.id, []) if st == "ready"),
                                          total=len(by_deck.get(d.id, []))),
                        icon=d.icon, icon_color=d.icon_color)
            for d in decks]


def delete_deck(deck_id: str) -> None:
    get_deck_row(deck_id)
    with session() as s:
        for table in (SlideRow, SlideVersionRow, RunRow, MessageRow, FindingRow):
            s.exec(delete(table).where(table.deck_id == deck_id))  # type: ignore[call-overload,attr-defined]
        s.exec(delete(DeckRow).where(DeckRow.id == deck_id))  # type: ignore[call-overload,arg-type]
        s.commit()
    from .media.router import delete_deck_media
    delete_deck_media(deck_id)


def delete_slides(deck_id: str, slide_ids: list[str]) -> None:
    """Delete slides with their versions and findings, then renumber the rest from 1."""
    if not slide_ids:
        return
    with session() as s:
        for table, column in ((SlideVersionRow, SlideVersionRow.slide_id), (FindingRow, FindingRow.slide_id),
                              (SlideRow, SlideRow.id)):
            s.exec(delete(table).where(column.in_(slide_ids)))  # type: ignore[call-overload,attr-defined]
        s.commit()
        rows = s.exec(select(SlideRow).where(SlideRow.deck_id == deck_id).order_by(SlideRow.position)).all()
        for position, row in enumerate(rows, start=1):
            if row.position != position:
                row.position = position
                s.add(row)
        s.commit()


# ---------------------------------------------------------------- deck and slide state
def update_deck(deck_id: str, **fields: Any) -> DeckRow:
    with session() as s:
        row = s.get(DeckRow, deck_id)
        if row is None:
            raise NotFound("That deck does not exist. It may have been deleted.")
        for name, value in fields.items():
            setattr(row, name, value)
        row.updated_at = now()
        s.add(row)
        s.commit()
        return row


def publish_deck(deck_id: str) -> None:
    try:
        row = get_deck_row(deck_id)
    except NotFound:
        return
    progress = progress_of(slide_rows(deck_id))
    bus.publish(deck_id, "deck.updated", {"status": row.status, "progress": progress.model_dump(),
                                          "paused": row.paused})


def set_slide_status(slide_id: str, status: str) -> None:
    with session() as s:
        row = s.get(SlideRow, slide_id)
        if row is None:
            return
        row.status = status
        s.add(row)
        s.commit()
    publish_slide(row)


def publish_slide(row: SlideRow) -> None:
    data: dict[str, Any] = {"slide_id": row.id, "index": row.position, "status": row.status,
                            "paused": row.id in HELD}
    if row.score is not None:
        data["score"] = row.score
    bus.publish(row.deck_id, "slide.updated", data)


def snapshot_of(row: SlideRow) -> dict[str, Any]:
    return {"headline": row.headline, "layout": row.layout, "nodes": row.nodes, "notes": row.notes,
            "section": row.section}


def save_slide(slide_id: str, reason: str, *, headline: str | None = None, layout: str | None = None,
               nodes: list[dict[str, Any]] | None = None, notes: str | None = None,
               section: str | None = None) -> tuple[SlideRow, str | None]:
    """Change a slide's content and record a slide_version. Returns (row, version id or None if unchanged)."""
    with session() as s:
        row = s.get(SlideRow, slide_id)
        if row is None:
            raise NotFound("That slide does not exist in this deck.")
        before = snapshot_of(row)
        if headline is not None:
            row.headline = headline
        if layout is not None:
            row.layout = layout
        if nodes is not None:
            row.nodes = nodes
        if notes is not None:
            row.notes = notes
        if section is not None:
            row.section = section or None
        after = snapshot_of(row)
        version_id = None
        if after != before:
            count = len(s.exec(select(SlideVersionRow.id).where(SlideVersionRow.slide_id == slide_id)).all())
            if count == 0:
                # Keep the starting point so the first change can be undone.
                s.add(SlideVersionRow(slide_id=slide_id, deck_id=row.deck_id, seq=1, reason="Before changes",
                                      snapshot=before))
                count = 1
            version = SlideVersionRow(slide_id=slide_id, deck_id=row.deck_id, seq=count + 1, reason=reason,
                                      snapshot=after)
            s.add(version)
            version_id = version.id
            deck = s.get(DeckRow, row.deck_id)
            if deck is not None:
                deck.updated_at = now()
                s.add(deck)
        s.add(row)
        s.commit()
        return row, version_id


_FIELDS = ("headline", "layout", "nodes", "notes", "section")


def undo_message(deck_id: str, message_id: str) -> dict[str, Any]:
    """Undo one Ask: revert exactly the slide versions that Ask created, and nothing else.

    The rule (also in server/README.md, "Undo"):
    - Each Ask records the slide versions it wrote (`message.version_ids`). Undo looks at each of those
      versions and the version just before it on the same slide, and for every field the Ask changed
      (headline, layout, nodes, notes, section) puts back the value from before the Ask.
    - A field changed again after the Ask (a manual edit, a later Ask) is left alone: that later change
      wins and the field is reported in `kept`. Fields the Ask did not touch are never written, so an
      earlier or later notes edit survives undoing a deck-wide Ask that rewrote headlines.
    - The revert is saved as a new version ("Undid: ..."), so a slide's own Undo can take it back.
    - Slides the Ask removed cannot be restored and are reported in `kept`. An Ask is undone once.
    """
    with session() as s:
        message = s.get(MessageRow, message_id)
        if message is None or message.deck_id != deck_id or message.role != "assistant":
            raise NotFound("That request does not exist in this deck.")
        if message.undone_at:
            raise Conflict("Those changes were already undone.")
        if not message.version_ids:
            raise Conflict("That request changed nothing that can be undone.")
        versions = [v for v in (s.get(SlideVersionRow, vid) for vid in message.version_ids) if v is not None]
        plans: dict[str, dict[str, Any]] = {}
        for version in versions:
            before = s.exec(select(SlideVersionRow).where(SlideVersionRow.slide_id == version.slide_id,
                                                          SlideVersionRow.seq < version.seq)
                            .order_by(SlideVersionRow.seq.desc())).first()  # type: ignore[attr-defined]
            if before is None:
                continue
            plan = plans.setdefault(version.slide_id, {})
            for field in _FIELDS:
                old, new = before.snapshot.get(field), version.snapshot.get(field)
                if old != new and field not in plan:
                    plan[field] = (old, new)        # the first version's "before" is the pre-Ask value
                elif field in plan:
                    plan[field] = (plan[field][0], new)
        reason = f"Undid: {(message.text or '')[:60]}"
    reverted: list[str] = []
    kept: list[dict[str, str]] = []
    for slide_id in message.changed_slide_ids or []:
        if slide_id not in plans:
            if not any(v.slide_id == slide_id for v in versions):
                kept.append({"slide_id": slide_id, "field": "slide", "reason": "removed"})
    for slide_id, plan in plans.items():
        with session() as s:
            row = s.get(SlideRow, slide_id)
        if row is None or row.deck_id != deck_id:
            kept.append({"slide_id": slide_id, "field": "slide", "reason": "removed"})
            continue
        current = snapshot_of(row)
        update: dict[str, Any] = {}
        for field, (old, new) in plan.items():
            if current.get(field) == new:
                update[field] = old if old is not None else ("" if field in {"notes", "headline"} else None)
            else:
                kept.append({"slide_id": slide_id, "field": field, "reason": "changed since"})
        if field_update := {k: v for k, v in update.items() if v is not None or k == "section"}:
            if "section" in field_update and field_update["section"] is None:
                field_update["section"] = ""
            save_slide(slide_id, reason, **field_update)
            reverted.append(slide_id)
    with session() as s:
        message = s.get(MessageRow, message_id)
        assert message is not None
        message.undone_at = now()
        s.add(message)
        s.commit()
    return {"reverted_slide_ids": reverted, "kept": kept}


def undo_slide(deck_id: str, slide_id: str) -> SlideRow:
    """Slide Undo: take back the latest change to this slide, whoever made it (a manual edit, an Ask, a
    fix), by dropping the latest slide_version and restoring the one before it. It steps back one
    version at a time, so it never skips over an edit to reach an older one."""
    get_slide_row(deck_id, slide_id)
    with session() as s:
        versions = s.exec(select(SlideVersionRow).where(SlideVersionRow.slide_id == slide_id)
                          .order_by(SlideVersionRow.seq.desc())).all()  # type: ignore[attr-defined]
        if len(versions) < 2:
            raise Conflict("There is nothing to undo on this slide.")
        latest, previous = versions[0], versions[1]
        row = s.get(SlideRow, slide_id)
        assert row is not None
        snap = previous.snapshot
        row.headline, row.layout = snap.get("headline", row.headline), snap.get("layout", row.layout)
        row.nodes, row.notes, row.section = snap.get("nodes", []), snap.get("notes", ""), snap.get("section")
        s.delete(latest)
        s.add(row)
        deck = s.get(DeckRow, deck_id)
        if deck is not None:
            deck.updated_at = now()
            s.add(deck)
        s.commit()
        return row


# ---------------------------------------------------------------- rules
def rule_texts() -> list[str]:
    with session() as s:
        return [r.text for r in s.exec(select(RuleRow).order_by(RuleRow.created_at)).all()]


def suppressed_lint_rules() -> set[str]:
    """Lint rule ids the user chose to keep: new findings of these start as `kept`."""
    with session() as s:
        rows = s.exec(select(RuleRow).where(RuleRow.source.like(f"{CRITIC_RULE_PREFIX}%"))).all()  # type: ignore[union-attr]
    return {(r.source or "")[len(CRITIC_RULE_PREFIX):] for r in rows}


# ---------------------------------------------------------------- findings
def to_finding(row: FindingRow, index: int) -> Finding:
    return Finding(id=row.id, slide_id=row.slide_id, slide_index=index, rule=row.rule,
                   severity=row.severity, title=row.title, detail=row.detail,  # type: ignore[arg-type]
                   status=row.status)  # type: ignore[arg-type]


def has_open_rule(slide_id: str, rule: str) -> bool:
    with session() as s:
        return s.exec(select(FindingRow.id).where(FindingRow.slide_id == slide_id, FindingRow.rule == rule,
                                                   FindingRow.status == "open")).first() is not None


def editable(row: SlideRow) -> bool:
    """A slide a person (or a fix) may change now: not mid-build. A slide held back after the build
    ("sent_back" because of template text) is editable, so it can be fixed."""
    if row.status in {"ready", "queued"}:
        return True
    return row.status == "sent_back" and get_deck_row(row.deck_id).status != "building"


def lint_and_sync(deck_id: str, slide_id: str, announce: bool = True) -> list[lint.Issue]:
    """Lint one slide, bring its finding rows in line, store its score. Returns the open issues."""
    deck = load_deck(deck_id)
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise NotFound("That slide does not exist in this deck.")
    issues = lint.lint_slide(slide, deck.theme, rule_texts(), context_for(deck.slides, slide))
    if deck.theme.brand_kit_id:  # brand kit rules (U09)
        from .brand.kits import kit_for_theme
        from .brand.rules import brand_issues
        kit = kit_for_theme(deck.theme)
        if kit is not None:
            issues += brand_issues(kit.rules, slide, deck.theme, context_for(deck.slides, slide))
    suppressed = suppressed_lint_rules()
    changed: list[FindingRow] = []
    open_issues: list[lint.Issue] = []
    with session() as s:
        existing = {f.key: f for f in s.exec(select(FindingRow).where(FindingRow.slide_id == slide_id)).all()}
        seen: set[str] = set()
        for issue in issues:
            seen.add(issue.fingerprint)
            row = existing.get(issue.fingerprint)
            if row is None:
                row = FindingRow(id=new_id("fd"), deck_id=deck_id, slide_id=slide_id, rule=issue.rule,
                                 key=issue.fingerprint, severity=issue.severity, title=issue.title,
                                 detail=issue.detail, status="kept" if issue.rule in suppressed else "open")
                changed.append(row)
            else:
                row.severity, row.title, row.detail = issue.severity, issue.title, issue.detail
                if row.status == "fixed":
                    row.status = "kept" if issue.rule in suppressed else "open"
                    changed.append(row)
            s.add(row)
            if row.status == "open":
                open_issues.append(issue)
        for key, row in existing.items():
            if key not in seen and row.status != "fixed":
                row.status = "fixed"
                s.add(row)
                changed.append(row)
        slide_row = s.get(SlideRow, slide_id)
        if slide_row is not None:
            slide_row.score = lint.slide_score(open_issues)
            s.add(slide_row)
        s.commit()
    if announce:
        for row in changed:
            bus.publish(deck_id, "finding.updated", {"id": row.id, "status": row.status})
    held = slide_row is not None and slide_row.status == "sent_back" and deck.status != "building"
    if held and not any(i.rule == "placeholder_text" for i in open_issues):
        set_slide_status(slide_id, "ready")   # the template text was fixed or kept
    return open_issues


def findings_for(deck_id: str) -> list[Finding]:
    rows = slide_rows(deck_id)
    index = {r.id: r.position for r in rows}
    with session() as s:
        found = s.exec(select(FindingRow).where(FindingRow.deck_id == deck_id)).all()
    order = {"open": 0, "kept": 1, "fixed": 2}
    severity = {"high": 0, "medium": 1, "low": 2}
    listed = [to_finding(f, index[f.slide_id]) for f in found if f.slide_id in index]
    return sorted(listed, key=lambda f: (order.get(f.status, 3), f.slide_index, severity.get(f.severity, 3)))
