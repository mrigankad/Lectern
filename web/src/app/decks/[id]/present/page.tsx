"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, CheckCircle2, Maximize, Minus, MonitorOff, MonitorUp, Plus, X } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ProductTile } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { errorText } from "@/lib/api";
import { cx } from "@/lib/format";
import { useDeck, useRender } from "@/lib/hooks";

type Sync = { type: "state"; index: number; black: boolean; ended?: boolean } | { type: "hello" };

function channelName(id: string) {
  return `lectern-present-${id}`;
}

function clock(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${String(m).padStart(2, "0")}:${sec}`;
}

/** Fits a 16:9 slide inside the window. */
function useFit(padding = 0) {
  const [size, setSize] = useState(0);
  useEffect(() => {
    const on = () => setSize(Math.max(0, Math.min(window.innerWidth - padding, ((window.innerHeight - padding) * 16) / 9)));
    on();
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [padding]);
  return size;
}

function Dark({ children }: { children: ReactNode }) {
  return <div className="flex h-dvh w-full items-center justify-center bg-[#0B0C0F] text-[15px] text-[#A9AEBA]">{children}</div>;
}

/* ---------- Audience view: slide only, follows the presenter ---------- */

function Audience({ id }: { id: string }) {
  const render = useRender(id);
  const [index, setIndex] = useState(0);
  const [black, setBlack] = useState(false);
  const [ended, setEnded] = useState(false);
  const width = useFit();

  useEffect(() => {
    const ch = new BroadcastChannel(channelName(id));
    ch.onmessage = (e: MessageEvent<Sync>) => {
      if (e.data.type !== "state") return;
      setIndex(e.data.index);
      setBlack(e.data.black);
      setEnded(Boolean(e.data.ended));
    };
    ch.postMessage({ type: "hello" } satisfies Sync);
    return () => ch.close();
  }, [id]);

  const slides = render.data ?? [];
  const slide = slides[Math.min(index, slides.length - 1)];
  if (render.isError) return <Dark>{errorText(render.error)}</Dark>;
  if (ended) return <Dark>The presentation has ended.</Dark>;
  return (
    <div className="flex h-dvh w-full items-center justify-center overflow-hidden bg-black" onDoubleClick={() => document.documentElement.requestFullscreen?.().catch(() => {})}>
      {slide && !black && width > 0 ? <SlideCanvas slide={slide} width={width} /> : null}
    </div>
  );
}

/** Fills the space it is given with the largest 16:9 slide that fits both its width and its height. */
function FitStage({ className, children }: { className?: string; children: (width: number) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const fit = () => setWidth(Math.floor(Math.min(node.clientWidth, (node.clientHeight * 16) / 9)));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(node);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className={cx("flex min-h-0 grow basis-0 items-start justify-center", className)}>
      {width > 0 ? children(width) : null}
    </div>
  );
}

/* ---------- Presenter view ---------- */

function Presenter({ id }: { id: string }) {
  const router = useRouter();
  const deck = useDeck(id);
  const render = useRender(id);
  const [index, setIndex] = useState(0);
  const [black, setBlack] = useState(false);
  const [noteSize, setNoteSize] = useState(20);
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(Date.now());
  const channel = useRef<BroadcastChannel | null>(null);

  const slides = render.data ?? [];
  const meta = deck.data?.slides ?? [];
  const total = slides.length;
  const current = slides[index];
  const next = slides[index + 1];
  const notes = meta.find((s) => s.id === current?.id)?.notes ?? meta[index]?.notes ?? "";
  const planned = (deck.data?.brief.minutes ?? 0) * 60;

  useEffect(() => {
    const t = setInterval(() => setElapsed((Date.now() - started.current) / 1000), 500);
    return () => clearInterval(t);
  }, []);

  const broadcast = useCallback((state: { index: number; black: boolean; ended?: boolean }) => {
    channel.current?.postMessage({ type: "state", ...state } satisfies Sync);
  }, []);

  useEffect(() => {
    const ch = new BroadcastChannel(channelName(id));
    channel.current = ch;
    return () => {
      ch.close();
      channel.current = null;
    };
  }, [id]);

  // Keep the latest state reachable from the channel's "hello" handler.
  const live = useRef({ index, black });
  live.current = { index, black };
  useEffect(() => {
    const ch = channel.current;
    if (!ch) return;
    ch.onmessage = (e: MessageEvent<Sync>) => {
      if (e.data.type === "hello") broadcast(live.current);
    };
  }, [broadcast, id]);

  useEffect(() => broadcast({ index, black }), [index, black, broadcast]);

  const go = useCallback((to: number) => setIndex(Math.max(0, Math.min(total - 1, to))), [total]);
  const end = useCallback(() => {
    broadcast({ index, black: true, ended: true });
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    router.push(`/decks/${id}`);
  }, [broadcast, index, id, router]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) {
        e.preventDefault();
        go(index + 1);
      } else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) {
        e.preventDefault();
        go(index - 1);
      } else if (e.key === "Home") go(0);
      else if (e.key === "End") go(total - 1);
      else if (e.key === "b" || e.key === "B" || e.key === ".") setBlack((b) => !b);
      else if (e.key === "Escape" && !document.fullscreenElement) end();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index, total, end]);

  // Pace: where we are against where the plan says we should be at this slide.
  const expected = planned && total ? (planned * index) / total : 0;
  const drift = Math.round(expected - elapsed);
  const perSlide = planned && total ? planned / total : 0;

  if (deck.isError || render.isError) return <Dark>{errorText(deck.error ?? render.error)}</Dark>;
  if (!deck.data || !render.data) return <Dark>Opening the presenter view</Dark>;
  if (total === 0) return <Dark>This deck has no slides to present yet.</Dark>;

  const btn = "inline-flex h-[52px] items-center gap-2.5 rounded-control border border-[#2E323B] bg-[#1C1F26] px-5 text-[15px] font-bold text-white hover:bg-[#252932]";

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-[#16181D] text-white">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[#2A2D35] px-5">
        <ProductTile size={28} />
        <span className="truncate text-[17px] font-bold">{deck.data.title}</span>
        <span className="hidden text-[13px] text-[#A9AEBA] md:inline">Presenter view · only you see this screen</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="inline-flex h-9 items-center gap-2 rounded-control px-3 text-[13px] font-bold text-white hover:bg-[#252932]"
            onClick={() => window.open(`/decks/${id}/present?view=audience`, `lectern-audience-${id}`, "popup,width=1280,height=720")}
          >
            <MonitorUp size={16} /> Open audience view
          </button>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-2 rounded-control px-3 text-[13px] font-bold text-white hover:bg-[#252932]"
            onClick={() => document.documentElement.requestFullscreen?.().catch(() => {})}
          >
            <Maximize size={16} /> Full screen
          </button>
        </div>
      </header>

      <div className="flex min-h-0 grow gap-10 px-10 pb-7 pt-7">
        <div className="flex min-w-0 grow basis-0 flex-col gap-3">
          <div className="flex items-end justify-between">
            <span className="text-[13px] font-bold text-[#A9AEBA]">{black ? "Audience sees a black screen" : "Now showing"}</span>
            <span className="text-[24px] font-bold leading-7">
              Slide {index + 1} <span className="text-[15px] font-normal text-[#A9AEBA]">of {total}</span>
            </span>
          </div>
          <FitStage className={cx(black && "opacity-40")}>{(w) => <SlideCanvas slide={current} width={w} className="rounded-card" />}</FitStage>
          <div className="flex gap-1.5" role="group" aria-label="Slides">
            {slides.map((s, i) => (
              <button
                key={s.id}
                type="button"
                aria-label={`Go to slide ${i + 1}`}
                aria-current={i === index ? "step" : undefined}
                onClick={() => go(i)}
                className={cx("h-1.5 grow rounded-pill", i === index ? "bg-action" : i < index ? "bg-[#5E6370]" : "bg-[#2E323B]")}
              />
            ))}
          </div>
          <div className="mt-auto flex flex-wrap items-center gap-2.5 pt-4">
            <button type="button" className={btn} onClick={() => go(index - 1)} disabled={index === 0}>
              <ArrowLeft size={18} /> Previous
            </button>
            <button type="button" className="btn-primary inline-flex h-[52px] items-center gap-2.5 rounded-control px-6 text-[15px] font-bold" onClick={() => go(index + 1)} disabled={index >= total - 1}>
              Next slide <ArrowRight size={18} />
            </button>
            <div className="ml-auto flex gap-2.5">
              <button type="button" className={cx(btn, black && "border-action bg-action-soft text-action hover:bg-action-soft")} aria-pressed={black} onClick={() => setBlack((b) => !b)}>
                <MonitorOff size={18} /> Black screen
              </button>
              <button type="button" className={btn} onClick={end}>
                <X size={18} /> End
              </button>
            </div>
          </div>
        </div>

        <aside className="flex w-[440px] shrink-0 flex-col gap-4">
          <div className="flex items-end justify-between gap-4 rounded-card bg-[#20232B] p-5">
            <div className="flex flex-col gap-1">
              <span className="text-[13px] font-bold text-[#A9AEBA]">Time elapsed</span>
              <span className="text-[52px] font-bold leading-[52px] tabular-nums" role="timer">{clock(elapsed)}</span>
            </div>
            <div className="flex flex-col items-end gap-1 text-right">
              {planned ? (
                <>
                  <span className="text-[15px] font-bold">of {clock(planned)} planned</span>
                  <span className={cx("flex items-center gap-1.5 text-[13px]", drift >= -30 ? "text-[#4ACB93]" : "text-[#FF8A8E]")}>
                    <CheckCircle2 size={14} />
                    {Math.abs(drift) < 15 ? "On pace" : drift > 0 ? `${clock(drift)} ahead` : `${clock(-drift)} behind`}
                  </span>
                </>
              ) : (
                <span className="text-[13px] text-[#A9AEBA]">No planned length</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 rounded-card bg-[#20232B] p-4">
            {next ? (
              <>
                <div className="w-[200px] shrink-0 overflow-hidden rounded-[8px]">
                  <SlideCanvas slide={next} width={200} />
                </div>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="text-[13px] font-bold text-[#A9AEBA]">Up next · Slide {index + 2}</span>
                  <span className="line-clamp-3 text-[16px] font-bold leading-5">{meta.find((s) => s.id === next.id)?.headline ?? ""}</span>
                  {perSlide ? <span className="text-[13px] text-[#A9AEBA]">Planned for {clock(perSlide)}</span> : null}
                </div>
              </>
            ) : (
              <span className="text-[14px] text-[#A9AEBA]">This is the last slide.</span>
            )}
          </div>

          <div className="flex min-h-0 grow flex-col gap-3 rounded-card bg-[#20232B] p-5">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-bold text-[#A9AEBA]">Speaker notes</span>
              <span className="flex items-center gap-2 text-[13px] font-bold">
                <button type="button" aria-label="Smaller notes" className="rounded-chip p-1 hover:bg-[#2E323B]" onClick={() => setNoteSize((n) => Math.max(14, n - 2))}>
                  <Minus size={16} />
                </button>
                Text size
                <button type="button" aria-label="Larger notes" className="rounded-chip p-1 hover:bg-[#2E323B]" onClick={() => setNoteSize((n) => Math.min(40, n + 2))}>
                  <Plus size={16} />
                </button>
              </span>
            </div>
            <div className="min-h-0 grow overflow-y-auto whitespace-pre-wrap" style={{ fontSize: noteSize, lineHeight: 1.45 }}>
              {notes.trim() || <span className="text-[#A9AEBA]">No notes for this slide.</span>}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Present() {
  const { id } = useParams<{ id: string }>();
  const view = useSearchParams().get("view");
  return view === "audience" ? <Audience id={id} /> : <Presenter id={id} />;
}

export default function PresentPage() {
  return (
    <Suspense fallback={null}>
      <Present />
    </Suspense>
  );
}
