"""The pipeline (SPEC section 4): outline, build with limited concurrency, one send-back loop,
chat edits, pause/resume and restart recovery. Work runs as asyncio tasks and reports through events."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

from sqlmodel import delete, select

from .. import config, store
from ..db import session
from ..engine import lint
from ..engine.place import context_for, place
from ..events import bus
from ..llm.base import LLMError
from ..models import DeckRow, FindingRow, MessageRow, RunRow, SlideRow, SlideVersionRow, now
from ..schema import Deck, Slide, TextNode
from . import analyst, apply, art_director, editor, renderer, runs, strategist, writer

log = logging.getLogger("lectern.pipeline")
ACTIVE_SLIDE_STATES = ("writing", "rendering", "checking", "sent_back")
LAYOUT_FINDINGS = frozenset({"empty_slot", "text_overflow"})


def _quote(text: str, limit: int = 70) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _name(layout: str) -> str:
    return layout.replace("_", " ")


def _finding_dicts(issues: list[lint.Issue]) -> list[dict[str, Any]]:
    return [{"rule": i.rule, "key": i.key, "severity": i.severity, "title": i.title, "detail": i.detail}
            for i in issues]


class Pipeline:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._extra: set[asyncio.Task[None]] = set()
        self._gates: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------ task plumbing
    def is_running(self, deck_id: str) -> bool:
        task = self._tasks.get(deck_id)
        return task is not None and not task.done()

    def _spawn(self, deck_id: str, work: Coroutine[Any, Any, None], primary: bool = True) -> asyncio.Task[None]:
        task = asyncio.create_task(self._guard(deck_id, work))
        if primary:
            self._tasks[deck_id] = task
        else:
            self._extra.add(task)
            task.add_done_callback(self._extra.discard)
        return task

    async def _guard(self, deck_id: str, work: Coroutine[Any, Any, None]) -> None:
        try:
            await work
        except asyncio.CancelledError:
            raise
        except store.NotFound:
            log.info("deck %s was deleted while work was running", deck_id)
        except Exception as error:  # a bug, not a provider failure: surface it instead of hanging the UI
            log.exception("pipeline task for deck %s failed", deck_id)
            try:
                store.update_deck(deck_id, status="failed", error=f"Something went wrong: {error}")
                store.publish_deck(deck_id)
            except store.NotFound:
                pass

    async def wait(self, deck_id: str) -> None:
        """Wait for the deck's current outline or build task (used by tests)."""
        task = self._tasks.get(deck_id)
        if task is not None:
            await asyncio.wait([task])

    def cancel(self, deck_id: str) -> None:
        task = self._tasks.pop(deck_id, None)
        if task is not None and not task.done():
            task.cancel()
        self._gates.pop(deck_id, None)

    async def shutdown(self) -> None:
        tasks = [t for t in [*self._tasks.values(), *self._extra] if not t.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _gate(self, deck_id: str) -> asyncio.Event:
        gate = self._gates.get(deck_id)
        if gate is None:
            gate = asyncio.Event()
            gate.set()
            self._gates[deck_id] = gate
        return gate

    # ------------------------------------------------------------ public entry points
    def start_outline(self, deck_id: str, instruction: str | None = None) -> None:
        if self.is_running(deck_id):
            raise store.Conflict("This deck is busy. Wait for the current step to finish.")
        store.update_deck(deck_id, status="draft", error=None, paused=False)
        store.publish_deck(deck_id)
        self._spawn(deck_id, self._outline(deck_id, instruction))

    def start_build(self, deck_id: str) -> None:
        if self.is_running(deck_id):
            raise store.Conflict("This deck is already being built.")
        rows = store.slide_rows(deck_id)
        if not rows:
            raise store.Conflict("There is no outline to build yet.")
        self._gate(deck_id).set()
        store.update_deck(deck_id, status="building", error=None, paused=False)
        store.publish_deck(deck_id)
        self._spawn(deck_id, self._build(deck_id))

    def pause(self, deck_id: str) -> None:
        deck = store.get_deck_row(deck_id)
        if deck.status != "building":
            raise store.Conflict("Only a deck that is being built can be paused.")
        self._gate(deck_id).clear()
        store.update_deck(deck_id, paused=True)
        store.publish_deck(deck_id)

    def resume(self, deck_id: str) -> None:
        deck = store.get_deck_row(deck_id)
        if self.is_running(deck_id):
            self._gate(deck_id).set()
            store.update_deck(deck_id, paused=False)
            store.publish_deck(deck_id)
            return
        if deck.status in {"building", "failed"} and store.slide_rows(deck_id):
            self.start_build(deck_id)      # nothing is running (restart or failure): pick the build back up
            return
        raise store.Conflict("There is no paused build to resume.")

    def start_ask(self, deck_id: str, message_id: str) -> None:
        self._spawn(deck_id, self._ask(deck_id, message_id), primary=False)

    # ------------------------------------------------------------ outline
    async def _outline(self, deck_id: str, instruction: str | None) -> None:
        deck = store.load_deck(deck_id)
        brief = analyst.prepare(deck_id, deck.brief.model_dump(exclude_none=True))
        current = None
        if deck.slides:
            current = {"title": deck.title, "slides": [
                {"section": s.section, "headline": s.headline, "layout": s.layout, "intent": s.intent}
                for s in deck.slides]}
        run = runs.start(deck_id, "strategist",
                         "Strategist is revising the outline." if instruction else
                         "Strategist is drafting the outline.")
        try:
            draft, result = await strategist.draft_outline(brief, store.rule_texts(), instruction, current)
        except LLMError as error:
            runs.finish(run, f"Strategist could not draft the outline: {error}", failed=True, error=str(error))
            store.update_deck(deck_id, status="failed", error=str(error))
            store.publish_deck(deck_id)
            return
        if not draft.slides:
            runs.finish(run, "Strategist returned an empty outline.", failed=True, error="empty outline")
            store.update_deck(deck_id, status="failed", error="The outline came back empty. Try again.")
            store.publish_deck(deck_id)
            return
        with session() as s:
            for table in (SlideRow, SlideVersionRow, FindingRow):
                s.exec(delete(table).where(table.deck_id == deck_id))  # type: ignore[call-overload,attr-defined]
            for position, item in enumerate(draft.slides, start=1):
                headline = item.headline.strip() or "Untitled slide"
                s.add(SlideRow(deck_id=deck_id, position=position, section=item.section, headline=headline,
                               layout=item.layout, intent=item.intent or None, status="queued", notes="",
                               nodes=[TextNode(role="headline", value=headline).model_dump()]))
            s.commit()
        new_brief = dict(brief)
        if draft.deck_type:
            new_brief["deck_type"] = draft.deck_type
        store.update_deck(deck_id, title=draft.title.strip() or deck.title, status="outline_ready",
                          brief=new_brief, error=None)
        count = len(draft.slides)
        runs.finish(run, f"Strategist drafted a {count}-slide outline"
                         f"{' as a ' + draft.deck_type.lower() if draft.deck_type else ''}.", result)
        bus.publish(deck_id, "outline.ready", {})
        store.publish_deck(deck_id)

    # ------------------------------------------------------------ build
    async def _build(self, deck_id: str) -> None:
        todo = [row for row in store.slide_rows(deck_id) if row.status != "ready"]
        semaphore = asyncio.Semaphore(config.BUILD_CONCURRENCY)
        results = await asyncio.gather(*(self._build_one(deck_id, row.id, semaphore) for row in todo),
                                       return_exceptions=True)
        for outcome in results:
            if isinstance(outcome, (asyncio.CancelledError, store.NotFound)):
                raise outcome
            if isinstance(outcome, BaseException) and not isinstance(outcome, LLMError):
                raise outcome
        failures = [r for r in results if isinstance(r, LLMError)]
        if failures:
            count = len(failures)
            store.update_deck(deck_id, status="failed", paused=False,
                              error=f"{count} slide{'s' if count != 1 else ''} could not be built: {failures[0]}")
        else:
            store.update_deck(deck_id, status="ready", paused=False, error=None)
        store.publish_deck(deck_id)

    async def _build_one(self, deck_id: str, slide_id: str, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            try:
                await self._build_slide(deck_id, slide_id)
            except LLMError:
                store.set_slide_status(slide_id, "queued")
                raise

    def _load(self, deck_id: str, slide_id: str) -> tuple[Deck, Slide, SlideRow]:
        deck = store.load_deck(deck_id)
        slide = next((s for s in deck.slides if s.id == slide_id), None)
        if slide is None:
            raise store.NotFound("That slide does not exist in this deck.")
        return deck, slide, store.get_slide_row(deck_id, slide_id)

    async def _hold(self, deck_id: str, slide_id: str) -> None:
        """Wait at the pause gate. While waiting, the slide reads `paused` (its status still names the last
        step), so the UI shows "Paused" instead of "Writing"; resume clears it and the step continues."""
        gate = self._gate(deck_id)
        if gate.is_set():
            return
        store.HELD.add(slide_id)
        self._publish_slide(slide_id)
        try:
            await gate.wait()
        finally:
            store.HELD.discard(slide_id)
            self._publish_slide(slide_id)

    @staticmethod
    def _publish_slide(slide_id: str) -> None:
        with session() as s:
            row = s.get(SlideRow, slide_id)
        if row is not None:
            store.publish_slide(row)

    async def _build_slide(self, deck_id: str, slide_id: str) -> None:
        await self._gate(deck_id).wait()   # not started yet: it stays "queued", which already reads as waiting
        store.set_slide_status(slide_id, "writing")
        await self._write(deck_id, slide_id, None)
        await self._hold(deck_id, slide_id)
        store.set_slide_status(slide_id, "rendering")
        await self._art_direct(deck_id, slide_id, None)
        await self._render(deck_id, slide_id)
        await self._request_image(deck_id, slide_id)
        await self._hold(deck_id, slide_id)
        store.set_slide_status(slide_id, "checking")
        blocking = await self._check(deck_id, slide_id, first=True)
        if blocking:
            store.set_slide_status(slide_id, "sent_back")
            findings = _finding_dicts(blocking)
            await self._hold(deck_id, slide_id)
            await self._write(deck_id, slide_id, findings)
            if any(issue.rule in LAYOUT_FINDINGS for issue in blocking):
                await self._art_direct(deck_id, slide_id, findings)
            await self._render(deck_id, slide_id)
            store.set_slide_status(slide_id, "checking")
            await self._check(deck_id, slide_id, first=False)
        # Template text left after the send-back keeps the slide out of "ready" until it is fixed or kept
        # (store.lint_and_sync releases it).
        store.set_slide_status(slide_id, "sent_back" if store.has_open_rule(slide_id, "placeholder_text")
                               else "ready")
        store.publish_deck(deck_id)

    async def _write(self, deck_id: str, slide_id: str, findings: list[dict[str, Any]] | None) -> None:
        deck, slide, row = self._load(deck_id, slide_id)
        n = slide.index
        run = runs.start(deck_id, "writer",
                         f"Writer is revising slide {n} after the Critic's review." if findings else
                         f"Writer is writing slide {n}.", row)
        outline = [{"index": s.index, "section": s.section, "headline": s.headline, "layout": s.layout}
                   for s in deck.slides]
        try:
            draft, result = await writer.write_slide(deck.brief.model_dump(exclude_none=True), deck.title,
                                                     outline, slide, store.rule_texts(), findings)
        except LLMError as error:
            runs.finish(run, f"Writer could not finish slide {n}: {error}", failed=True, error=str(error))
            raise
        written = apply.patched(slide, headline=draft.headline, nodes=draft.nodes, notes=draft.notes)
        apply.save(deck_id, written, "Writer revision" if findings else "Writer draft", lint=False,
                   announce=False)
        runs.finish(run, (f"Writer revised slide {n}: “{_quote(written.headline)}”." if findings else
                          f"Writer wrote slide {n}: “{_quote(written.headline)}”."), result)

    async def _art_direct(self, deck_id: str, slide_id: str, findings: list[dict[str, Any]] | None) -> None:
        deck, slide, row = self._load(deck_id, slide_id)
        n = slide.index
        run = runs.start(deck_id, "art_director", f"Art Director is choosing the layout for slide {n}.", row)
        neighbours = [s.layout for s in deck.slides if abs(s.index - n) == 1]
        try:
            choice, result = await art_director.choose_layout(slide, neighbours, store.rule_texts(), findings)
        except LLMError as error:
            runs.finish(run, f"Art Director could not review slide {n}: {error}", failed=True, error=str(error))
            raise
        if choice.layout != slide.layout:
            changed = apply.patched(slide, layout=choice.layout)
            apply.save(deck_id, changed, f"Art Director: {_name(slide.layout)} to {_name(choice.layout)}",
                       lint=False, announce=False)
            runs.finish(run, f"Art Director changed slide {n} from {_name(slide.layout)} to "
                             f"{_name(choice.layout)}.", result)
        else:
            runs.finish(run, f"Art Director kept the {_name(slide.layout)} layout for slide {n}.", result)

    async def _request_image(self, deck_id: str, slide_id: str) -> None:
        """Art Director: ask for a picture on a slide that needs one, when a media provider is configured
        (or offline placeholders are switched on with the `auto_images` setting). Never blocks the build."""
        from ..media import router as media

        deck, slide, row = self._load(deck_id, slide_id)
        provider_id = media.auto_provider()
        if provider_id is None or not media.needs_image(slide):
            return
        n = slide.index
        run = runs.start(deck_id, "art_director", f"Art Director is requesting an image for slide {n}.", row)
        try:
            asset = await media.auto_image(deck_id, slide, deck.theme)
        except Exception as error:  # a failed picture must not fail the slide
            runs.finish(run, f"Art Director could not get an image for slide {n}: {error}", failed=True,
                        error=str(error))
            return
        if asset is None:
            runs.finish(run, f"Art Director found no image for slide {n}.", model=provider_id)
            return
        changed = apply.patched(slide, nodes=media.with_image(slide, asset).nodes)
        apply.save(deck_id, changed, "Art Director: added an image", lint=False, announce=False)
        runs.finish(run, f"Art Director added a {provider_id} image to slide {n}.", model=provider_id)

    async def _render(self, deck_id: str, slide_id: str) -> None:
        deck, slide, row = self._load(deck_id, slide_id)
        n = slide.index
        run = runs.start(deck_id, "renderer", f"Renderer is laying out slide {n}.", row)
        result = None
        normal = renderer.normalize(slide)
        if renderer.missing(normal):
            try:
                draft, result = await renderer.repair(deck.brief.model_dump(exclude_none=True), normal,
                                                      store.rule_texts())
            except LLMError as error:
                runs.finish(run, f"Renderer could not complete slide {n}: {error}", failed=True, error=str(error))
                raise
            normal = apply.patched(normal, headline=draft.headline, nodes=draft.nodes, notes=draft.notes)
        apply.save(deck_id, normal, "Renderer: fitted to layout", lint=False, announce=False)
        count = len(place(normal, deck.theme, context_for(deck.slides, normal)).elements)
        gaps = renderer.missing(normal)
        runs.finish(run, (f"Renderer laid out slide {n}, but the {_name(normal.layout)} layout is still missing "
                          f"{', '.join(gaps)}." if gaps else
                          f"Renderer laid out slide {n} in the {_name(normal.layout)} layout "
                          f"({count} objects, all editable)."), result, model="layout")

    async def _check(self, deck_id: str, slide_id: str, first: bool) -> list[lint.Issue]:
        """Critic step. Returns the issues worth a send-back."""
        _deck, slide, row = self._load(deck_id, slide_id)
        n = slide.index
        run = runs.start(deck_id, "critic", f"Critic is checking slide {n}.", row)
        delay = config.offline_delay()
        if delay:
            await asyncio.sleep(delay / 2)
        issues = store.lint_and_sync(deck_id, slide_id)
        score = store.get_slide_row(deck_id, slide_id).score
        blocking = [issue for issue in issues if lint.is_blocking(issue)]
        if blocking and first:
            more = f" and {len(blocking) - 1} more" if len(blocking) > 1 else ""
            summary = f"Critic sent slide {n} back: {blocking[0].title.lower()}{more}."
        elif issues:
            count = len(issues)
            summary = (f"Critic scored slide {n} at {score}: {count} thing{'s' if count != 1 else ''} "
                       "left for you to review.")
        else:
            summary = f"Critic passed slide {n} with a score of {score}."
        runs.finish(run, summary, model="lint")
        return blocking if first else []

    # ------------------------------------------------------------ ask (chat edits)
    async def _ask(self, deck_id: str, message_id: str) -> None:
        with session() as s:
            message = s.get(MessageRow, message_id)
        if message is None:
            return
        deck = store.load_deck(deck_id)
        brief = deck.brief.model_dump(exclude_none=True)
        rules = store.rule_texts()
        version_ids: list[str] = []
        changed_ids: list[str] = []
        target = next((s for s in deck.slides if s.id == message.slide_id), None)
        row = store.get_slide_row(deck_id, target.id) if target else None
        run = runs.start(deck_id, "editor", (f"Editor is working on slide {target.index}." if target else
                                             "Editor is working through the deck."), row)
        try:
            if message.scope == "slide" and target is not None:
                edit, result = await editor.edit_slide(brief, target, message.text, rules)
                summary = edit.summary
                if any(v is not None for v in (edit.headline, edit.layout, edit.nodes, edit.notes)):
                    changed = apply.patched(target, headline=edit.headline, layout=edit.layout, nodes=edit.nodes,
                                            notes=edit.notes)
                    _row, version_id = apply.save(deck_id, changed, f"Chat: {_quote(message.text, 60)}")
                    if version_id:
                        version_ids.append(version_id)
                        changed_ids.append(target.id)
            else:
                deck_edit, result = await editor.edit_deck(brief, deck.title, deck.slides, message.text, rules)
                summary = deck_edit.summary
                by_id = {s.id: s for s in deck.slides}
                for change in deck_edit.changes:
                    slide = by_id.get(change.slide_id)
                    if slide is None:
                        continue
                    changed = apply.patched(slide, headline=change.headline, layout=change.layout,
                                            nodes=change.nodes, notes=change.notes)
                    _row, version_id = apply.save(deck_id, changed, f"Chat: {_quote(message.text, 60)}")
                    if version_id:
                        version_ids.append(version_id)
                        changed_ids.append(slide.id)
                removable = [sid for sid in dict.fromkeys(deck_edit.remove_slide_ids)
                             if sid in by_id and sid != deck.slides[0].id]
                if removable and len(removable) < len(deck.slides):
                    store.delete_slides(deck_id, removable)
                    changed_ids.extend(sid for sid in removable if sid not in changed_ids)
                    store.publish_deck(deck_id)
                if deck_edit.title and deck_edit.title.strip() and deck_edit.title != deck.title:
                    store.update_deck(deck_id, title=deck_edit.title.strip())
                    store.publish_deck(deck_id)
        except LLMError as error:
            runs.finish(run, f"Editor could not make that change: {error}", failed=True, error=str(error))
            self._finish_message(deck_id, message_id, "failed", str(error), [], [])
            return
        count = len(changed_ids)
        runs.finish(run, (f"Editor changed {count} slide{'s' if count != 1 else ''}." if count else
                          "Editor made no changes."), result)
        self._finish_message(deck_id, message_id, "done", summary, version_ids, changed_ids)

    def _finish_message(self, deck_id: str, message_id: str, status: str, result: str,
                        version_ids: list[str], changed_ids: list[str]) -> None:
        with session() as s:
            row = s.get(MessageRow, message_id)
            if row is None:
                return
            row.status, row.result, row.text = status, result, result
            row.version_ids, row.changed_slide_ids = version_ids, changed_ids
            s.add(row)
            s.commit()
        bus.publish(deck_id, "message.updated", {"id": message_id, "status": status, "result": result})


def recover() -> None:
    """After a restart nothing is running: mark interrupted work so the UI can offer Retry."""
    with session() as s:
        for run in s.exec(select(RunRow).where(RunRow.status == "running")).all():
            run.status = "failed"
            run.error = "interrupted"
            run.summary = f"{run.summary.rstrip('.')} (interrupted when Lectern restarted)."
            run.ended_at = now()
            s.add(run)
        for slide in s.exec(select(SlideRow).where(SlideRow.status.in_(ACTIVE_SLIDE_STATES))).all():  # type: ignore[attr-defined]
            slide.status = "queued"
            s.add(slide)
        for deck in s.exec(select(DeckRow).where(DeckRow.status.in_(("building", "draft")))).all():  # type: ignore[attr-defined]
            deck.error = ("The build was interrupted when Lectern restarted. Retry to continue from where it "
                          "stopped." if deck.status == "building" else
                          "The outline was interrupted when Lectern restarted. Try again.")
            deck.status = "failed"
            deck.paused = False
            s.add(deck)
        for message in s.exec(select(MessageRow).where(MessageRow.status == "pending")).all():
            message.status = "failed"
            message.result = "Interrupted when Lectern restarted. Ask again."
            message.text = message.result
            s.add(message)
        s.commit()


pipeline = Pipeline()
