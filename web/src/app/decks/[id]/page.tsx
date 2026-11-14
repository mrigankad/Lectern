"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { BrandKitPicker } from "@/components/BrandKitPicker";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Check, ClipboardCheck, Download, LayoutTemplate, Link2, MessageSquare, MonitorPlay, Minus, Plus, StickyNote, Undo2 } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { deckProblem, LayoutIcon } from "@/components/DeckStates";
import { AppShell, StepChip } from "@/components/Shell";
import { SlideCanvas, SlidePlaceholder } from "@/components/SlideCanvas";
import { AiCard, Button, ErrorState, InlineError, LinkButton, LoadingState, Segmented, Spinner } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { canEditElement, textEditPatch } from "@/lib/edit";
import { useDeckEvents } from "@/lib/events";
import { cx, layoutName, sayTime } from "@/lib/format";
import { useDeck, useDeckGate, useRender } from "@/lib/hooks";
import type { Deck, LayoutId, Message, RenderedSlide, Slide, SlideElement, SlidePatch } from "@/lib/types";

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const SUGGESTIONS = ["Shorten the headline", "Add a source line", "Try another layout"];

function resultText(m: Message): string | null {
  if (!m.result) return null;
  return typeof m.result === "string" ? m.result : (m.result.summary ?? m.result.text ?? null);
}

/* ---------- Speaker notes ---------- */

function Notes({ slide, onSave, disabled }: { slide: Slide; onSave: (notes: string) => void; disabled: boolean }) {
  const [text, setText] = useState(slide.notes);
  const saved = useRef(slide.notes);
  const focused = useRef(false);

  // Notes changed on the server (an agent edit, an undo): take them unless the person is typing.
  useEffect(() => {
    if (slide.notes !== saved.current && !focused.current) {
      saved.current = slide.notes;
      setText(slide.notes);
    }
  }, [slide.notes]);

  const commit = useCallback(
    (value: string) => {
      if (value === saved.current) return;
      saved.current = value;
      onSave(value);
    },
    [onSave],
  );

  useEffect(() => {
    if (text === saved.current) return;
    const t = setTimeout(() => commit(text), 1200);
    return () => clearTimeout(t);
  }, [text, commit]);

  return (
    <div className="flex h-[148px] shrink-0 flex-col gap-2 border-t border-line bg-bg px-6 py-3.5">
      <div className="flex items-center justify-between">
        <label htmlFor="notes" className="label flex items-center gap-2">
          <StickyNote size={15} aria-hidden /> Speaker notes
        </label>
        <span className="text-[12px] leading-4 text-body">{sayTime(text)}</span>
      </div>
      <textarea
        id="notes"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => (focused.current = true)}
        onBlur={() => {
          focused.current = false;
          commit(text);
        }}
        placeholder="What you will say out loud on this slide. It is saved as you type and goes into the PowerPoint notes."
        className="min-h-0 grow resize-none bg-transparent text-[14px] leading-[21px] text-ink placeholder:text-muted disabled:opacity-60"
      />
    </div>
  );
}

/* ---------- Ask panel ---------- */

function AskPanel({ deck, slide }: { deck: Deck; slide: Slide | undefined }) {
  const qc = useQueryClient();
  const messages = useQuery({ queryKey: keys.messages(deck.id), queryFn: () => api.getMessages(deck.id) });
  const [text, setText] = useState("");
  const [scope, setScope] = useState<"slide" | "deck">("slide");
  const end = useRef<HTMLDivElement>(null);
  const count = messages.data?.length ?? 0;

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [count]);

  const send = useMutation({
    mutationFn: (message: string) => api.ask(deck.id, { scope, slide_id: scope === "slide" ? slide?.id : undefined, message }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: keys.messages(deck.id) });
    },
  });
  const undo = useMutation({
    mutationFn: (messageId: string) => api.undoMessage(deck.id, messageId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.messages(deck.id) });
      qc.invalidateQueries({ queryKey: keys.deck(deck.id) });
      qc.invalidateQueries({ queryKey: keys.render(deck.id) });
    },
  });

  const canSend = text.trim().length > 0 && !send.isPending && (scope === "deck" || Boolean(slide));
  const submit = (value = text) => {
    if (value.trim() && (scope === "deck" || slide)) send.mutate(value.trim());
  };
  const slideNumber = (sid?: string | null) => deck.slides.find((s) => s.id === sid)?.index;

  return (
    <div className="flex min-h-0 grow flex-col">
      <div className="flex min-h-0 grow flex-col gap-4 overflow-y-auto p-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-[17px] font-bold leading-6 text-ink">Say what to change</h2>
          <p className="text-[13px] leading-[19px] text-body">Plain words are fine. Every change can be undone.</p>
        </div>

        {messages.isPending ? (
          <LoadingState label="Loading earlier requests" className="py-6" />
        ) : messages.isError ? (
          <ErrorState title="Earlier requests could not be loaded" message={errorText(messages.error)} onRetry={() => messages.refetch()} />
        ) : count === 0 ? (
          <p className="rounded-control bg-surface px-3 py-2.5 text-[13px] leading-[19px] text-body">
            Nothing asked yet. Try one of the suggestions below, or describe the change you want.
          </p>
        ) : (
          messages.data.map((m) => {
            const result = resultText(m);
            const isUser = m.role !== "assistant";
            const pending = isUser && !result && m.status !== "done" && m.status !== "failed";
            const n = slideNumber(m.slide_id);
            return (
              <div key={m.id} className="flex flex-col gap-2">
                {isUser ? (
                  <div className="flex flex-col gap-0.5 rounded-control bg-surface px-3 py-2.5">
                    <span className="text-[12px] leading-4 text-body">You · {m.scope === "deck" ? "whole deck" : n ? `slide ${n}` : "a slide"}</span>
                    <span className="text-[14px] font-bold leading-5 text-ink">{m.text}</span>
                  </div>
                ) : m.status === "failed" ? (
                  <p className="rounded-control bg-fail-soft px-3 py-2.5 text-[13px] leading-[19px] text-ink">{result ?? m.text}</p>
                ) : (
                  // The backend answers in a separate assistant message; its Undo lives here.
                  <AiCard className="flex flex-col gap-1.5 px-3 py-2.5">
                    <span className="flex gap-2 text-[13px] leading-[19px] text-ink">
                      {m.changed_slide_ids?.length ? <Check size={15} className="mt-0.5 shrink-0 text-pass" aria-hidden /> : null}
                      {result ?? m.text}
                    </span>
                    {m.undone ? (
                      <span className="text-[13px] leading-[19px] text-body">Undone</span>
                    ) : m.version_ids?.length ? (
                      <button
                        type="button"
                        disabled={undo.isPending}
                        onClick={() => undo.mutate(m.id)}
                        className="self-start text-[13px] font-bold text-ink underline underline-offset-2 disabled:opacity-50"
                      >
                        Undo
                      </button>
                    ) : null}
                  </AiCard>
                )}
                {!isUser ? null : pending ? (
                  <AiCard className="flex items-center gap-2 px-3 py-2.5 text-[13px] text-ink" >
                    <Spinner size={15} /> The Editor is working on it
                  </AiCard>
                ) : m.status === "failed" ? (
                  <p className="rounded-control bg-fail-soft px-3 py-2.5 text-[13px] leading-[19px] text-ink">
                    {result ?? "That change did not go through. Nothing on the slide was altered. Try asking again."}
                  </p>
                ) : isUser && result ? (
                  <AiCard className="flex flex-col gap-1.5 px-3 py-2.5">
                    <span className="flex gap-2 text-[13px] leading-[19px] text-ink">
                      <Check size={15} className="mt-0.5 shrink-0 text-pass" aria-hidden /> {result}
                    </span>
                    {m.version_ids?.length && !m.undone ? (
                      <button
                        type="button"
                        disabled={undo.isPending}
                        onClick={() => undo.mutate(m.id)}
                        className="self-start pl-[23px] text-[13px] font-bold text-ink underline underline-offset-2 disabled:opacity-50"
                      >
                        Undo
                      </button>
                    ) : null}
                  </AiCard>
                ) : null}
              </div>
            );
          })
        )}
        <InlineError>{undo.isError ? errorText(undo.error) : null}</InlineError>
        <div ref={end} />
      </div>

      <div className="flex shrink-0 flex-col gap-2.5 border-t border-line p-4">
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              disabled={send.isPending || !slide}
              onClick={() => {
                setScope("slide");
                send.mutate(s);
              }}
              className="rounded-chip border border-line-strong px-2.5 py-1 text-[13px] font-bold leading-4 text-ink hover:bg-surface disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-2.5 rounded-control border border-line-strong p-2.5 focus-within:border-action">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (canSend) submit();
              }
            }}
            rows={2}
            aria-label="Ask for a change"
            placeholder={scope === "slide" ? "Ask for a change to this slide" : "Ask for a change to the whole deck"}
            className="resize-none bg-transparent text-[14px] leading-5 text-ink placeholder:text-muted"
          />
          <div className="flex items-center justify-between">
            <Segmented label="What to change" value={scope} onChange={setScope} options={[{ value: "slide", label: "This slide" }, { value: "deck", label: "Whole deck" }]} />
            <Button variant="primary" size="sm" className="w-[30px] px-0" aria-label="Send" disabled={!canSend} busy={send.isPending} onClick={() => submit()}>
              {send.isPending ? null : <ArrowUp size={16} />}
            </Button>
          </div>
        </div>
        <InlineError>{send.isError ? errorText(send.error) : null}</InlineError>
      </div>
    </div>
  );
}

/* ---------- Design panel ---------- */

function DesignPanel({ slide, onPick, busy }: { slide: Slide | undefined; onPick: (layout: LayoutId) => void; busy: boolean }) {
  const layouts = useQuery({ queryKey: keys.layouts, queryFn: api.listLayouts, staleTime: Infinity });
  return (
    <div className="flex min-h-0 grow flex-col gap-3 overflow-y-auto p-4">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-[17px] font-bold leading-6 text-ink">Layout</h2>
        <p className="text-[13px] leading-[19px] text-body">Pick how this slide is arranged. The words stay; a layout only shows the content it has room for.</p>
      </div>
      {layouts.isPending ? (
        <LoadingState label="Loading layouts" className="py-6" />
      ) : layouts.isError ? (
        <ErrorState title="Layouts could not be loaded" message={errorText(layouts.error)} onRetry={() => layouts.refetch()} />
      ) : !slide ? (
        <p className="text-[13px] text-body">Pick a slide first.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {layouts.data.map((l) => {
            const current = l.id === slide.layout;
            return (
              <li key={l.id}>
                <button
                  type="button"
                  disabled={busy}
                  aria-pressed={current}
                  onClick={() => !current && onPick(l.id)}
                  className={cx(
                    "flex w-full items-center gap-3 rounded-control border px-3 py-2 text-left disabled:opacity-60",
                    current ? "border-action bg-action-soft" : "border-line hover:border-line-strong hover:bg-surface",
                  )}
                >
                  <span className={cx("flex shrink-0", current ? "text-action" : "text-body")}>
                    <LayoutIcon layout={l.id} size={18} />
                  </span>
                  <span className="flex min-w-0 grow flex-col">
                    <span className="text-[14px] font-bold leading-[18px] text-ink">{l.name || layoutName(l.id)}</span>
                    <span className="truncate text-[12px] leading-4 text-body">{l.purpose}</span>
                  </span>
                  {current ? <Check size={16} className="shrink-0 text-action" aria-label="Current layout" /> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/* ---------- Workspace ---------- */

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const qc = useQueryClient();
  const query = useDeck(id);
  const deck = query.data;
  const redirecting = useDeckGate(deck, "workspace", params.get("view") === "slides");
  useDeckEvents(id);
  const render = useRender(id, Boolean(deck));

  const [picked, setPicked] = useState<string | null>(params.get("slide"));
  const [tab, setTab] = useState<"ask" | "design">("ask");
  const [zoom, setZoom] = useState(2);

  const slides = deck ? [...deck.slides].sort((a, b) => a.index - b.index) : [];
  const slide = slides.find((s) => s.id === picked) ?? slides.find((s) => s.status === "ready") ?? slides[0];
  const rendered = new Map<string, RenderedSlide>((render.data ?? []).map((r) => [r.id, r]));
  const current = slide ? rendered.get(slide.id) : undefined;
  const building = deck?.status === "building";
  const editable = slide?.status === "ready";

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.deck(id) });
    qc.invalidateQueries({ queryKey: keys.render(id) });
    qc.invalidateQueries({ queryKey: keys.critic(id) });
  };
  const patch = useMutation({
    mutationFn: ({ sid, body }: { sid: string; body: SlidePatch }) => api.patchSlide(id, sid, body),
    onSettled: refresh,
  });
  const undo = useMutation({ mutationFn: (sid: string) => api.undoSlide(id, sid), onSettled: refresh });
  const mutatePatch = patch.mutate;

  const onEditText = useCallback(
    (el: SlideElement, text: string) => {
      if (!slide) return;
      const body = textEditPatch(slide, el, text);
      if (body) mutatePatch({ sid: slide.id, body });
    },
    [slide, mutatePatch],
  );
  const canEdit = useCallback((el: SlideElement) => Boolean(slide && editable && canEditElement(slide, el)), [slide, editable]);
  const saveNotes = useCallback((notes: string) => slide && mutatePatch({ sid: slide.id, body: { notes } }), [slide, mutatePatch]);

  const problem = deckProblem(query, redirecting);
  const saveState = patch.isPending || undo.isPending ? "Saving" : patch.isError ? `Not saved: ${errorText(patch.error)}` : undo.isError ? errorText(undo.error) : "All changes saved";

  return (
    <AppShell
      flush
      crumbs={[{ label: "Home", href: "/" }, { label: deck?.title || "Deck" }]}
      chip={<StepChip step={5} />}
      actions={
        deck && !problem ? (
          <>
            <span className={cx("hidden max-w-[260px] truncate text-[12px] xl:inline", patch.isError || undo.isError ? "text-fail" : "text-body")} role="status">
              {saveState}
            </span>
            <Button size="sm" variant="ghost" disabled={!slide || undo.isPending} onClick={() => slide && undo.mutate(slide.id)} title="Undo the last change to this slide">
              <Undo2 size={15} /> Undo
            </Button>
            <LinkButton href={`/decks/${id}/present`} size="sm">
              <MonitorPlay size={15} /> Present
            </LinkButton>
            <LinkButton href={`/decks/${id}/share`} size="sm">
              <Link2 size={15} /> Share
            </LinkButton>
            <LinkButton href={`/decks/${id}/review`} size="sm">
              <ClipboardCheck size={15} /> Critic report
            </LinkButton>
            <LinkButton href={`/decks/${id}/export`} size="sm" variant="primary">
              <Download size={15} /> Export
            </LinkButton>
          </>
        ) : null
      }
    >
      {problem ? (
        <div className="w-full p-10">{problem}</div>
      ) : deck && slides.length === 0 ? (
        <div className="w-full p-10">
          <ErrorState title="This deck has no slides" message="Something went wrong while it was built. Make a new deck from the same brief.">
            <LinkButton href="/new" size="sm">
              New deck
            </LinkButton>
          </ErrorState>
        </div>
      ) : deck ? (
        <>
          {/* Slide rail */}
          <nav aria-label="Slides" className="flex w-[164px] shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-line py-2.5">
            {slides.map((s) => {
              const r = rendered.get(s.id);
              const on = s.id === slide?.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  aria-current={on}
                  aria-label={`Slide ${s.index}: ${s.headline}`}
                  onClick={() => setPicked(s.id)}
                  className={cx("flex shrink-0 gap-2 px-2.5 py-1.5 text-left", on ? "bg-action-soft" : "hover:bg-surface")}
                >
                  <span className={cx("w-4 shrink-0 pt-0.5 text-[12px] font-bold leading-4", on ? "text-action" : "text-muted")}>{s.index}</span>
                  <span className={cx("overflow-hidden rounded-chip border", on ? "border-action shadow-[0_0_0_1px_var(--action)]" : "border-line-strong")}>
                    {r ? <SlideCanvas slide={r} width={118} /> : <SlidePlaceholder width={118} label={s.status === "ready" ? "" : "…"} />}
                  </span>
                </button>
              );
            })}
          </nav>

          {/* Stage and notes */}
          <div className="flex min-w-0 grow basis-0 flex-col">
            {building ? (
              <div className="flex shrink-0 items-center gap-2 border-b border-line bg-action-soft px-5 py-2 text-[13px] text-ink">
                <Spinner size={15} /> This deck is still being built. Finished slides can be edited now.
                <Link href={`/decks/${id}/build`} className="font-bold underline underline-offset-2">
                  Back to the build
                </Link>
              </div>
            ) : null}
            <div className="flex min-h-0 grow basis-0 flex-col bg-surface-2">
              <div className="flex h-11 shrink-0 items-center justify-between px-5 text-[13px] leading-4">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="shrink-0 font-bold text-ink">
                    Slide {slide?.index} of {slides.length}
                  </span>
                  <span className="truncate text-body">
                    {[slide?.section, slide ? `${layoutName(slide.layout)} layout` : null].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button type="button" aria-label="Zoom out" disabled={zoom === 0} onClick={() => setZoom(zoom - 1)} className="flex size-7 items-center justify-center rounded-chip hover:bg-bg disabled:opacity-30">
                    <Minus size={16} />
                  </button>
                  <button type="button" onClick={() => setZoom(2)} className="rounded-chip px-2 py-1 font-bold text-ink hover:bg-bg" title="Fit the slide to the window">
                    {zoom === 2 ? "Fit" : `${Math.round(ZOOMS[zoom] * 100)}%`}
                  </button>
                  <button type="button" aria-label="Zoom in" disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom(zoom + 1)} className="flex size-7 items-center justify-center rounded-chip hover:bg-bg disabled:opacity-30">
                    <Plus size={16} />
                  </button>
                </div>
              </div>
              <div className="min-h-0 grow basis-0 overflow-auto px-8 pb-8 pt-2 [scrollbar-gutter:stable]">
                <div
                  className="mx-auto overflow-hidden rounded-chip border border-line-strong bg-bg"
                  style={{ width: `${ZOOMS[zoom] * 100}%`, maxWidth: zoom === 2 ? "calc((100dvh - 372px) * 16 / 9)" : undefined }}
                >
                  {current ? (
                    <SlideCanvas key={current.id} slide={current} canEdit={canEdit} onEditText={onEditText} />
                  ) : render.isError ? (
                    <div className="p-6">
                      <ErrorState title="This slide could not be drawn" message={errorText(render.error)} onRetry={() => render.refetch()} />
                    </div>
                  ) : (
                    <div className="flex aspect-video flex-col items-center justify-center gap-2 text-[14px] text-body">
                      {render.isPending || slide?.status !== "ready" ? <Spinner /> : null}
                      {render.isPending ? "Drawing the slide" : slide?.status === "ready" ? "This slide has nothing to show yet." : "This slide is still being built."}
                    </div>
                  )}
                </div>
                {current && editable ? <p className="pt-3 text-center text-[12px] text-body">Click any text on the slide to edit it. Enter saves, Escape cancels.</p> : null}
              </div>
            </div>
            {slide ? <Notes key={slide.id} slide={slide} onSave={saveNotes} disabled={!editable} /> : null}
          </div>

          {/* Ask / Design */}
          <aside className="flex w-[340px] shrink-0 flex-col border-l border-line">
            <div role="tablist" className="flex h-11 shrink-0 border-b border-line px-2">
              {([["ask", "Ask", MessageSquare], ["design", "Design", LayoutTemplate]] as const).map(([key, label, Icon]) => (
                <button
                  key={key}
                  role="tab"
                  type="button"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={cx(
                    "flex grow items-center justify-center gap-2 border-b-2 text-[14px] font-bold",
                    tab === key ? "border-action text-ink" : "border-transparent text-body hover:text-ink",
                  )}
                >
                  <Icon size={16} aria-hidden /> {label}
                </button>
              ))}
            </div>
            {tab === "ask" ? (
              <AskPanel deck={deck} slide={slide} />
            ) : (
              <div className="flex min-h-0 grow flex-col overflow-y-auto">
                <BrandKitPicker deck={deck} />
                <DesignPanel slide={slide} busy={patch.isPending || !editable} onPick={(layout) => slide && patch.mutate({ sid: slide.id, body: { layout } })} />
              </div>
            )}
          </aside>
        </>
      ) : null}
    </AppShell>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
