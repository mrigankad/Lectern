"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Compass, Eye, Layers, LayoutTemplate, MessageSquare, Pause, Pencil, Play, RotateCw, Undo2, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { deckProblem } from "@/components/DeckStates";
import { AppShell, StepChip } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { Button, Card, ErrorState, InlineError, LinkButton, PageHeader, Pill, Spinner } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { useDeckEvents, type ActivityItem } from "@/lib/events";
import { cx, pad2, plural, roleName, timeAgo } from "@/lib/format";
import { useDeck, useDeckGate, useRender } from "@/lib/hooks";
import type { RenderedSlide, Slide, SlideStatus } from "@/lib/types";

const ROLE_ICONS: Record<string, LucideIcon> = {
  strategist: Compass,
  writer: Pencil,
  art_director: LayoutTemplate,
  renderer: Layers,
  critic: Eye,
  editor: MessageSquare,
};

const WORDS: Record<SlideStatus, string> = {
  queued: "queued",
  writing: "being written",
  rendering: "rendering",
  checking: "being checked",
  sent_back: "sent back",
  ready: "ready",
};

function useNow(everyMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(t);
  }, [everyMs]);
  return now;
}

function StatusLabel({ status, held, pausing }: { status: SlideStatus; held?: boolean; pausing?: boolean }) {
  // Paused build: a slide whose next step waits for Resume says so instead of its last step's name.
  if (held && status !== "ready" && status !== "queued") {
    return (
      <span className="flex items-center gap-1 text-warn">
        <Pause size={14} aria-hidden /> Paused
      </span>
    );
  }
  if (pausing && status !== "ready" && status !== "queued") {
    return <span className="flex items-center gap-1 text-body">Finishing, then pausing</span>;
  }
  switch (status) {
    case "ready":
      return (
        <span className="flex items-center gap-1 text-pass">
          <Check size={14} strokeWidth={2.5} aria-hidden /> Ready
        </span>
      );
    case "checking":
      return (
        <span className="flex items-center gap-1 text-ink">
          <Eye size={14} aria-hidden /> Critic is checking
        </span>
      );
    case "sent_back":
      return (
        <span className="flex items-center gap-1 text-warn">
          <Undo2 size={14} aria-hidden /> Sent back
        </span>
      );
    case "rendering":
      return (
        <span className="flex items-center gap-1 text-body">
          <Layers size={14} aria-hidden /> Rendering
        </span>
      );
    case "writing":
      return (
        <span className="flex items-center gap-1 text-body">
          <Pencil size={14} aria-hidden /> Writing
        </span>
      );
    default:
      return <span className="text-muted">Queued</span>;
  }
}

function Tile({ slide, rendered, deckPaused }: { slide: Slide; rendered?: RenderedSlide; deckPaused?: boolean }) {
  const drawn = rendered && (slide.status === "ready" || slide.status === "checking" || slide.status === "sent_back");
  return (
    <li className="flex flex-col gap-2">
      <div
        className={cx(
          "overflow-hidden rounded-control border",
          slide.status === "checking" ? "border-action shadow-[0_0_0_1px_var(--action)]" : slide.status === "sent_back" ? "border-warn" : slide.status === "queued" ? "border-dashed border-line-strong" : "border-line",
        )}
      >
        {drawn ? (
          <div className={cx(slide.status === "sent_back" && "opacity-50")}>
            <SlideCanvas slide={rendered} />
          </div>
        ) : slide.status === "queued" ? (
          <div className="flex aspect-video items-center justify-center text-[28px] font-bold text-line-strong">{slide.index}</div>
        ) : (
          <div className={cx("flex aspect-video flex-col justify-between bg-surface p-3", !slide.paused && !deckPaused && "pulse")} aria-hidden>
            <div className="flex flex-col gap-1.5">
              <div className="h-2.5 w-3/5 rounded-pill bg-surface-2" />
              <div className="h-2.5 w-2/5 rounded-pill bg-surface-2" />
            </div>
            <div className="flex gap-2">
              <div className="h-12 grow rounded-chip bg-surface-2" />
              <div className="h-12 grow rounded-chip bg-surface-2" />
              <div className="h-12 grow rounded-chip bg-surface-2" />
            </div>
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 text-[13px] leading-4">
        <span className="w-5 shrink-0 font-bold text-muted">{pad2(slide.index)}</span>
        <span className={cx("min-w-0 grow truncate font-bold", slide.status === "queued" ? "text-body" : "text-ink")} title={slide.headline}>
          {slide.headline}
        </span>
        <span className="shrink-0 text-[12px] font-bold">
          <StatusLabel status={slide.status} held={slide.paused} pausing={deckPaused && !slide.paused} />
        </span>
      </div>
    </li>
  );
}

function Activity({ items, building, paused }: { items: ActivityItem[]; building: boolean; paused: boolean }) {
  const now = useNow(5_000);
  return (
    <Card className="flex w-[340px] shrink-0 flex-col overflow-hidden">
      <div className="flex items-baseline justify-between px-4 pb-2.5 pt-3.5">
        <h2 className="text-[15px] font-bold leading-5 text-ink">Who is doing what</h2>
        <span className="text-[12px] text-body">Live activity</span>
      </div>
      {items.length === 0 ? (
        <div className="flex items-center gap-2.5 border-t border-line px-4 py-4 text-[13px] leading-[19px] text-body">
          {building && !paused ? <Spinner size={16} /> : null}
          {paused ? "Paused. Nothing happens until you resume." : building ? "Waiting for the next step. Each agent reports here as it works." : "Nothing is running right now."}
        </div>
      ) : (
        <ol aria-live="polite">
          {items.map((item) => {
            const Icon = ROLE_ICONS[item.role] ?? Compass;
            const running = item.status === "running" || item.status === "started";
            const failed = item.status === "failed" || item.status === "error";
            return (
              <li key={item.id} className="flex gap-3 border-t border-line px-4 py-3">
                <span
                  className={cx(
                    "flex size-[26px] shrink-0 items-center justify-center rounded-pill",
                    failed ? "bg-fail-soft text-fail" : running ? "bg-ai-soft text-ai" : "bg-surface-2 text-body",
                  )}
                >
                  <Icon size={14} aria-hidden />
                </span>
                <div className="flex min-w-0 grow flex-col gap-0.5">
                  <div className="flex justify-between gap-2">
                    <span className="text-[14px] font-bold leading-[18px] text-ink">
                      {roleName(item.role)}
                      {failed ? " found a problem" : ""}
                    </span>
                    <span className={cx("shrink-0 text-[12px] leading-[18px]", running ? "font-bold text-ai-ink" : "text-muted")}>{running ? "Now" : timeAgo(item.at, now)}</span>
                  </div>
                  <span className="text-[13px] leading-[18px] text-body">{item.summary}</span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

export default function BuildPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const query = useDeck(id);
  const deck = query.data;
  const redirecting = useDeckGate(deck, "build");
  useDeckEvents(id);
  const render = useRender(id, Boolean(deck));
  const activity = useQuery<ActivityItem[]>({ queryKey: keys.activity(id), queryFn: () => [], staleTime: Infinity, gcTime: Infinity, enabled: false });
  const [pausedLocal, setPausedLocal] = useState<boolean | null>(null);

  // What already happened before this page opened. The endpoint is an extra the backend offers;
  // if it is missing the feed simply starts empty and fills from live events.
  const history = useQuery({ queryKey: ["runs", id], queryFn: () => api.getRuns(id), retry: false, staleTime: Infinity, enabled: Boolean(deck) });
  useEffect(() => {
    if (!history.data?.length) return;
    qc.setQueryData<ActivityItem[]>(keys.activity(id), (old = []) => {
      const seen = new Set(old.map((item) => item.id));
      const past = history.data
        .filter((r) => !seen.has(r.id))
        .map((r) => ({ ...r, at: Date.parse(r.ended_at ?? r.started_at ?? "") || Date.now() }));
      return [...old, ...past].sort((a, b) => b.at - a.at).slice(0, 40);
    });
  }, [history.data, id, qc]);

  const refresh = () => qc.invalidateQueries({ queryKey: keys.deck(id) });
  const pause = useMutation({
    mutationFn: (next: boolean) => (next ? api.pause(id) : api.resume(id)),
    onSuccess: (_d, next) => {
      setPausedLocal(next);
      refresh();
    },
  });
  // Retry after a failure: approving again restarts the slides that are not ready.
  const retry = useMutation({
    mutationFn: () => api.approve(id),
    onSuccess: refresh,
  });

  const problem = deckProblem(query, redirecting);
  const slides = deck ? [...deck.slides].sort((a, b) => a.index - b.index) : [];
  const byId = new Map((render.data ?? []).map((r) => [r.id, r]));
  const ready = slides.filter((s) => s.status === "ready").length;
  const paused = deck?.paused ?? pausedLocal ?? false;
  const failed = deck?.status === "failed";
  const counts = (["checking", "sent_back", "rendering", "writing", "queued"] as SlideStatus[])
    .map((s) => [slides.filter((x) => x.status === s).length, WORDS[s]] as const)
    .filter(([n]) => n > 0)
    .map(([n, word]) => `${n} ${word}`)
    .join(" · ");

  return (
    <AppShell crumbs={[{ label: "Home", href: "/" }, { label: deck?.title || "Deck" }, { label: "Build" }]} chip={<StepChip step={4} />}>
      {problem ?? (
        <>
          <PageHeader
            title={`${ready} of ${plural(slides.length, "slide")} ready`}
            subtitle={failed ? "The build stopped before it finished." : paused ? "The build is paused." : "Agents are writing, laying out and checking each slide. You can open the finished ones now."}
            actions={
              <>
                {failed ? <Pill tone="fail">Stopped</Pill> : paused ? <Pill tone="warn">Paused</Pill> : <Pill tone="action">Building</Pill>}
                {!failed ? (
                  <Button size="sm" busy={pause.isPending} onClick={() => pause.mutate(!paused)}>
                    {paused ? <Play size={15} /> : <Pause size={15} />} {paused ? "Resume" : "Pause"}
                  </Button>
                ) : null}
                {ready > 0 ? (
                  <LinkButton href={`/decks/${id}?view=slides`} variant="primary" size="sm">
                    Open finished slides <ArrowRight size={15} />
                  </LinkButton>
                ) : (
                  <Button variant="primary" size="sm" disabled title="No slide is finished yet">
                    Open finished slides <ArrowRight size={15} />
                  </Button>
                )}
              </>
            }
          />
          <InlineError>{pause.isError ? errorText(pause.error) : null}</InlineError>

          {failed ? (
            <ErrorState
              title="The build stopped"
              message={deck?.error || "An agent did not finish, most likely because the server restarted or a model did not answer. The finished slides are safe."}
            >
              <Button size="sm" variant="primary" busy={retry.isPending} onClick={() => retry.mutate()}>
                <RotateCw size={15} /> Retry the build
              </Button>
              {retry.isError ? <span className="text-[13px] text-fail">{errorText(retry.error)}</span> : null}
            </ErrorState>
          ) : null}

          <div className="flex flex-col gap-2">
            <div className="flex h-2 gap-[3px]" role="progressbar" aria-valuemin={0} aria-valuemax={slides.length} aria-valuenow={ready} aria-label="Slides ready">
              {slides.map((s) => (
                <div key={s.id} className={cx("grow basis-0 rounded-pill", s.status === "ready" ? "bg-[image:var(--action-gradient)]" : s.status === "queued" ? "bg-surface-2" : "bg-action-line")} />
              ))}
            </div>
            <div className="text-[13px] leading-4 text-body">{counts || "Every slide is ready."}</div>
          </div>

          <div className="flex items-start gap-4">
            <ol className="grid min-w-0 grow basis-0 grid-cols-2 gap-x-5 gap-y-6 lg:grid-cols-3 2xl:grid-cols-4">
              {slides.map((s) => (
                <Tile key={s.id} slide={s} rendered={byId.get(s.id)} deckPaused={paused} />
              ))}
            </ol>
            <Activity items={activity.data ?? []} building={deck?.status === "building"} paused={paused} />
          </div>
        </>
      )}
    </AppShell>
  );
}
