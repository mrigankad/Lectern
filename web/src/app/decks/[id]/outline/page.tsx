"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowRight, ArrowUp, Check, GripVertical, ListFilter, Pencil, Plus, RotateCw, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { deckProblem, LayoutIcon } from "@/components/DeckStates";
import { AppShell, StepChip } from "@/components/Shell";
import { AiCard, Button, Card, InlineError, PageHeader, Pill, SelectChip, Spinner } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { useDeckEvents } from "@/lib/events";
import { cx, LAYOUT_IDS, layoutName, pad2, plural, talkMinutes } from "@/lib/format";
import { useDeck, useDeckGate } from "@/lib/hooks";
import type { Deck, LayoutId } from "@/lib/types";

type Row = { key: string; id?: string; section: string; headline: string; layout: LayoutId; intent?: string | null };

const LAYOUT_OPTIONS = LAYOUT_IDS.map((id) => ({ value: id, label: layoutName(id) }));
let localKey = 0;

function rowsFrom(deck: Deck): Row[] {
  return [...deck.slides]
    .sort((a, b) => a.index - b.index)
    .map((s) => ({ key: s.id, id: s.id, section: s.section ?? "", headline: s.headline, layout: s.layout, intent: s.intent }));
}

function EditRow({ row, number, onSave, onCancel }: { row: Row; number: number; onSave: (headline: string, layout: LayoutId) => void; onCancel: () => void }) {
  const [headline, setHeadline] = useState(row.headline);
  const [layout, setLayout] = useState<LayoutId>(row.layout);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const save = () => (headline.trim() ? onSave(headline.trim(), layout) : onCancel());
  return (
    <li className="flex items-center gap-3 border-t border-line bg-action-soft px-4 py-2.5">
      <span className="w-[18px] shrink-0" />
      <span className="w-6 shrink-0 text-[13px] font-bold text-ink">{pad2(number)}</span>
      <input
        ref={input}
        value={headline}
        onChange={(e) => setHeadline(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") onCancel();
        }}
        aria-label={`Headline of slide ${number}`}
        placeholder="Write the headline as a claim, for example: Churn doubled in two quarters"
        className="h-9 min-w-0 grow rounded-control border border-action bg-bg px-3 text-[15px] ring-2 ring-action-soft font-bold text-ink placeholder:font-normal placeholder:text-muted"
      />
      <SelectChip icon={<LayoutIcon layout={layout} />} ariaLabel="Layout" value={layout} onChange={(v) => setLayout(v as LayoutId)} options={LAYOUT_OPTIONS} className="w-[176px]" />
      <Button variant="ink" size="sm" className="w-[30px] px-0" aria-label="Save changes to this slide" onClick={save}>
        <Check size={16} />
      </Button>
      <Button variant="ghost" size="sm" className="w-[30px] px-0" aria-label="Cancel" onClick={onCancel}>
        <X size={16} />
      </Button>
    </li>
  );
}

export default function OutlinePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const query = useDeck(id);
  const deck = query.data;
  const redirecting = useDeckGate(deck, "outline");

  const [rows, setRows] = useState<Row[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [redrafting, setRedrafting] = useState(false);
  const [drag, setDrag] = useState<{ key: string; over: string | null } | null>(null);
  const version = useRef(0);
  const synced = useRef<string | null>(null);

  useDeckEvents(id, () => {
    setRedrafting(false);
    synced.current = null;
  });

  // Take the server's outline whenever it changes and there is nothing unsaved here.
  useEffect(() => {
    if (!deck || dirty || deck.status !== "outline_ready") return;
    const stamp = `${deck.updated_at}:${deck.slides.length}`;
    if (synced.current === stamp) return;
    synced.current = stamp;
    setRows(rowsFrom(deck));
    setRedrafting(false);
  }, [deck, dirty]);

  const save = useMutation({
    mutationFn: (payload: { rows: Row[]; v: number }) =>
      api.putOutline(id, {
        title: deck?.title ?? "",
        slides: payload.rows.map((r) => ({ id: r.id, section: r.section || undefined, headline: r.headline, layout: r.layout })),
      }),
    onSuccess: async (_data, payload) => {
      if (payload.v !== version.current) return; // newer edits are waiting
      synced.current = null;
      await qc.invalidateQueries({ queryKey: keys.deck(id) });
      setDirty(false);
    },
  });
  const saveNow = save.mutateAsync;

  const change = useCallback((next: Row[]) => {
    version.current += 1;
    setRows(next);
    setDirty(true);
  }, []);

  // Save a moment after the last edit.
  useEffect(() => {
    if (!dirty || editing) return;
    const complete = rows.filter((r) => r.headline.trim());
    if (!complete.length) return;
    const v = version.current;
    const t = setTimeout(() => saveNow({ rows: complete, v }).catch(() => {}), 700);
    return () => clearTimeout(t);
  }, [dirty, rows, editing, saveNow]);

  const regenerate = useMutation({
    mutationFn: (instruction?: string) => api.regenerateOutline(id, instruction),
    onMutate: () => {
      setRedrafting(true);
      setEditing(null);
      setDirty(false);
    },
    onSuccess: () => {
      synced.current = null;
      qc.invalidateQueries({ queryKey: keys.deck(id) });
    },
    onError: () => setRedrafting(false),
  });

  const approve = useMutation({
    mutationFn: async () => {
      const complete = rows.filter((r) => r.headline.trim());
      if (dirty) await api.putOutline(id, { title: deck?.title ?? "", slides: complete.map((r) => ({ id: r.id, section: r.section || undefined, headline: r.headline, layout: r.layout })) });
      return api.approve(id);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: keys.deck(id) });
      qc.invalidateQueries({ queryKey: keys.decks });
      router.push(`/decks/${id}/build`);
    },
  });

  const sections = useMemo(() => {
    const out: { name: string; rows: { row: Row; i: number }[] }[] = [];
    rows.forEach((row, i) => {
      const last = out[out.length - 1];
      if (last && last.name === row.section) last.rows.push({ row, i });
      else out.push({ name: row.section, rows: [{ row, i }] });
    });
    return out;
  }, [rows]);

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= rows.length) return;
    const next = rows.map((r) => ({ ...r }));
    if (next[j].section !== next[i].section) next[i].section = next[j].section; // step across the section line
    else [next[i], next[j]] = [next[j], next[i]];
    change(next);
  }

  function drop(targetKey: string) {
    if (!drag || drag.key === targetKey) return setDrag(null);
    const moving = rows.find((r) => r.key === drag.key);
    const target = rows.find((r) => r.key === targetKey);
    setDrag(null);
    if (!moving || !target) return;
    const rest = rows.filter((r) => r.key !== drag.key);
    rest.splice(rest.findIndex((r) => r.key === targetKey), 0, { ...moving, section: target.section });
    change(rest);
  }

  function addSlide() {
    const key = `new-${++localKey}`;
    const section = rows[rows.length - 1]?.section ?? "";
    setRows([...rows, { key, section, headline: "", layout: "bullets" }]);
    setEditing(key);
  }

  const problem = deckProblem(query, redirecting);
  const drafting = !problem && (deck?.status === "draft" || redrafting);
  const count = rows.length;
  const minutes = talkMinutes(count);
  const slot = deck?.brief.minutes;
  const busy = approve.isPending || regenerate.isPending;

  return (
    <AppShell crumbs={[{ label: "Home", href: "/" }, { label: deck?.title || "Deck" }, { label: "Outline" }]} chip={<StepChip step={3} />}>
      {problem ??
        (drafting ? (
          <div className="flex flex-col items-center gap-3 py-20 text-center" role="status">
            <Spinner size={28} />
            <h1 className="text-[28px] font-bold leading-8 text-ink">The Strategist is drafting your outline</h1>
            <p className="max-w-[520px] text-[15px] leading-[22px] text-body">
              It is working out what the deck must say and in what order. This usually takes under a minute, and the outline appears here by itself.
            </p>
            {deck?.brief.prompt ? (
              <AiCard className="mt-3 max-w-[620px] p-4 text-left text-[14px] leading-[21px] text-ink">
                <div className="pb-1 text-[12px] font-bold text-ai-ink">Your brief</div>
                <span className="line-clamp-4">{deck.brief.prompt}</span>
              </AiCard>
            ) : null}
          </div>
        ) : (
          <>
            <PageHeader
              title="Is this the story you want to tell?"
              subtitle="Every headline is a claim. Reorder, rewrite or cut before the deck is built. Nothing is designed yet."
              actions={
                <span className="text-[13px] text-body" role="status">
                  {save.isError ? <span className="text-fail">Not saved: {errorText(save.error)}</span> : dirty || save.isPending ? "Saving" : "All changes saved"}
                </span>
              }
            />
            <div className="flex items-start gap-4">
              <div className="flex min-w-0 grow basis-0 flex-col gap-4">
                {count === 0 ? (
                  <Card className="p-6 text-[14px] text-body">The outline is empty. Add a slide, or ask for a new outline.</Card>
                ) : (
                  sections.map((section, si) => (
                    <Card key={`${section.name}-${si}`} className="overflow-hidden">
                      <div className="flex items-baseline justify-between px-4 pb-2.5 pt-3.5">
                        <h2 className="text-[15px] font-bold leading-5 text-ink">{section.name || "Slides"}</h2>
                        <span className="text-[12px] leading-4 text-body">
                          {plural(section.rows.length, "slide")} · about {talkMinutes(section.rows.length)} min
                        </span>
                      </div>
                      <ol>
                        {section.rows.map(({ row, i }) =>
                          editing === row.key ? (
                            <EditRow
                              key={row.key}
                              row={row}
                              number={i + 1}
                              onCancel={() => {
                                setEditing(null);
                                if (!row.headline) setRows(rows.filter((r) => r.key !== row.key));
                              }}
                              onSave={(headline, layout) => {
                                setEditing(null);
                                change(rows.map((r) => (r.key === row.key ? { ...r, headline, layout } : r)));
                              }}
                            />
                          ) : (
                            <li
                              key={row.key}
                              onDragOver={(e) => {
                                if (!drag) return;
                                e.preventDefault();
                                if (drag.over !== row.key) setDrag({ ...drag, over: row.key });
                              }}
                              onDrop={() => drop(row.key)}
                              className={cx(
                                "group flex min-h-[46px] items-center gap-3 border-t border-line px-4 py-1.5",
                                drag?.over === row.key && drag.key !== row.key && "shadow-[inset_0_2px_0_var(--action)]",
                                drag?.key === row.key && "opacity-40",
                              )}
                            >
                              <span
                                draggable
                                onDragStart={(e) => {
                                  e.dataTransfer.effectAllowed = "move";
                                  setDrag({ key: row.key, over: null });
                                }}
                                onDragEnd={() => setDrag(null)}
                                className="flex w-[18px] shrink-0 cursor-grab justify-center text-muted active:cursor-grabbing"
                                title="Drag to reorder"
                              >
                                <GripVertical size={16} aria-hidden />
                              </span>
                              <span className="w-6 shrink-0 text-[13px] font-bold text-muted">{pad2(i + 1)}</span>
                              <button type="button" onClick={() => setEditing(row.key)} className="flex min-w-0 grow basis-0 flex-col text-left" title="Click to rewrite">
                                <span className="truncate text-[15px] font-bold leading-5 text-ink">{row.headline}</span>
                                {row.intent ? <span className="truncate text-[13px] leading-[18px] text-body">{row.intent}</span> : null}
                              </button>
                              <span className="flex w-[132px] shrink-0 items-center gap-2 text-[13px] text-body">
                                <LayoutIcon layout={row.layout} /> {layoutName(row.layout)}
                              </span>
                              <span className="flex shrink-0 items-center opacity-0 focus-within:opacity-100 group-hover:opacity-100">
                                <IconButton label={`Move slide ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                                  <ArrowUp size={15} />
                                </IconButton>
                                <IconButton label={`Move slide ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}>
                                  <ArrowDown size={15} />
                                </IconButton>
                              </span>
                              <IconButton label={`Rewrite slide ${i + 1}`} onClick={() => setEditing(row.key)}>
                                <Pencil size={15} />
                              </IconButton>
                              <IconButton label={`Delete slide ${i + 1}`} disabled={rows.length <= 1} onClick={() => change(rows.filter((r) => r.key !== row.key))}>
                                <Trash2 size={15} />
                              </IconButton>
                            </li>
                          ),
                        )}
                      </ol>
                    </Card>
                  ))
                )}
              </div>

              <div className="flex w-[340px] shrink-0 flex-col gap-4">
                <AiCard className="flex flex-col gap-3 p-4">
                  <div className="flex items-center gap-2">
                    <span className="text-[15px] font-bold leading-5 text-ink">Story shape</span>
                    <Pill tone="ai" className="bg-bg">Strategist</Pill>
                  </div>
                  <ol className="flex flex-col gap-1 rounded-control bg-bg px-3 py-2.5">
                    {sections.map((s, si) => {
                      const from = s.rows[0].i + 1;
                      const to = s.rows[s.rows.length - 1].i + 1;
                      return (
                        <li key={si} className="flex justify-between gap-3 text-[12px] leading-4">
                          <span className="truncate text-ink">{s.name || "Slides"}</span>
                          <span className="shrink-0 text-body">{from === to ? `Slide ${from}` : `Slides ${from} to ${to}`}</span>
                        </li>
                      );
                    })}
                  </ol>
                  <div className="flex items-center gap-3">
                    <span className="text-[32px] font-bold leading-9 text-ink">{minutes} min</span>
                    <span className="flex flex-col text-[12px] leading-4 text-body">
                      <span className="font-bold text-ink">Estimated talk time</span>
                      {slot ? (minutes <= slot ? `Fits your ${slot} minute slot` : `Runs over your ${slot} minute slot`) : "At a minute and a half a slide"}
                    </span>
                  </div>
                </AiCard>

                <Card className="flex flex-col gap-3 p-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-[15px] font-bold leading-5 text-ink">Your decision</span>
                    <span className="text-[13px] leading-[19px] text-body">
                      Nothing is built until you approve. Building takes a few minutes, and you can still change anything after.
                    </span>
                  </div>
                  <Button variant="primary" size="lg" className="justify-between" busy={approve.isPending} disabled={busy || count === 0 || editing !== null} onClick={() => approve.mutate()}>
                    Approve and build <ArrowRight size={18} />
                  </Button>
                  <div className="flex gap-2">
                    <Button className="grow" disabled={busy} onClick={addSlide}>
                      <Plus size={16} /> Add slide
                    </Button>
                    <Button className="grow" disabled={busy} onClick={() => regenerate.mutate("make it shorter")}>
                      <ListFilter size={16} /> Make it shorter
                    </Button>
                  </div>
                  <Button disabled={busy} onClick={() => regenerate.mutate(undefined)}>
                    <RotateCw size={16} /> Regenerate outline
                  </Button>
                  <InlineError>{approve.isError ? errorText(approve.error) : regenerate.isError ? errorText(regenerate.error) : null}</InlineError>
                </Card>
              </div>
            </div>
          </>
        ))}
    </AppShell>
  );
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="flex size-7 shrink-0 items-center justify-center rounded-chip text-body hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
    >
      {children}
    </button>
  );
}
