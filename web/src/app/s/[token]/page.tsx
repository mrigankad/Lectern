"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Download, Lock } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ProductTile } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { Button, ErrorState, InlineError, LoadingState } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { cx } from "@/lib/format";
import type { SharedDeck } from "@/lib/types";

function visitorId(): string | undefined {
  try {
    let v = localStorage.getItem("lectern-visitor");
    if (!v) {
      v = Math.random().toString(36).slice(2, 14);
      localStorage.setItem("lectern-visitor", v);
    }
    return v;
  } catch {
    return undefined;
  }
}

/** Counts the seconds spent on each slide and reports them in small batches. */
function useViewTiming(token: string, shared: SharedDeck | undefined, slideId: string | undefined) {
  const since = useRef(Date.now());
  const current = useRef<string | undefined>(undefined);
  const flush = useCallback(() => {
    const sid = current.current;
    const seconds = (Date.now() - since.current) / 1000;
    since.current = Date.now();
    if (!shared || !sid || seconds < 0.5 || document.visibilityState === "hidden") return;
    api.pingShare(token, shared.view_id, sid, Math.min(seconds, 600)).catch(() => {});
  }, [shared, token]);

  useEffect(() => {
    flush();
    current.current = slideId;
  }, [slideId, flush]);

  useEffect(() => {
    const t = setInterval(flush, 10_000);
    const onHide = () => {
      if (document.visibilityState === "hidden") {
        const sid = current.current;
        const seconds = (Date.now() - since.current) / 1000;
        since.current = Date.now();
        if (shared && sid && seconds >= 0.5) api.pingShare(token, shared.view_id, sid, Math.min(seconds, 600)).catch(() => {});
      } else since.current = Date.now();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", onHide);
      flush();
    };
  }, [flush, shared, token]);
}

function Viewer({ token, shared }: { token: string; shared: SharedDeck }) {
  const [index, setIndex] = useState(0);
  const total = shared.render.length;
  const slide = shared.render[index];
  const meta = shared.slides[index];
  useViewTiming(token, shared, meta?.id);

  const go = useCallback((to: number) => setIndex(Math.max(0, Math.min(total - 1, to))), [total]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowRight", "PageDown", " "].includes(e.key)) {
        e.preventDefault();
        go(index + 1);
      } else if (["ArrowLeft", "PageUp"].includes(e.key)) {
        e.preventDefault();
        go(index - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  return (
    <div className="flex min-h-dvh w-full flex-col bg-surface">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-bg px-4 sm:px-6">
        <ProductTile size={24} />
        <span className="min-w-0 grow truncate text-[16px] font-bold text-ink">{shared.title}</span>
        {shared.allow_download ? (
          <a href={api.shareDownloadUrl(token, shared.view_id)} className="btn-primary inline-flex h-9 shrink-0 items-center gap-2 rounded-control px-3.5 text-[14px] font-bold">
            <Download size={16} /> Download
          </a>
        ) : null}
      </header>
      <main className="mx-auto flex w-full max-w-[1200px] grow flex-col gap-4 px-4 py-6 sm:px-6">
        {slide ? (
          <div className="overflow-hidden rounded-card border border-line bg-bg">
            <SlideCanvas slide={slide} />
          </div>
        ) : (
          <ErrorState title="No slides yet" message="This deck has no slides to show yet." />
        )}
        <div className="flex items-center gap-3">
          <Button onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous slide">
            <ArrowLeft size={16} /> <span className="hidden sm:inline">Previous</span>
          </Button>
          <div className="flex grow gap-1" aria-hidden>
            {shared.render.map((s, i) => (
              <span key={s.id} className={cx("h-1.5 grow rounded-pill", i === index ? "bg-action" : "bg-line-strong")} />
            ))}
          </div>
          <span className="shrink-0 text-[13px] text-body">
            {index + 1} / {total}
          </span>
          <Button variant="primary" onClick={() => go(index + 1)} disabled={index >= total - 1} aria-label="Next slide">
            <span className="hidden sm:inline">Next</span> <ArrowRight size={16} />
          </Button>
        </div>
        {shared.show_notes && meta?.notes ? (
          <section className="flex flex-col gap-1.5 rounded-card border border-line bg-bg p-5">
            <h2 className="text-[13px] font-bold text-body">Speaker notes</h2>
            <p className="whitespace-pre-wrap text-[16px] leading-6 text-ink">{meta.notes}</p>
          </section>
        ) : null}
      </main>
    </div>
  );
}

export default function SharedDeckPage() {
  const { token } = useParams<{ token: string }>();
  const probe = useQuery({ queryKey: ["share-probe", token], queryFn: () => api.probeShare(token), retry: false });
  const [password, setPassword] = useState("");
  const open = useMutation({ mutationFn: (pw?: string) => api.openShare(token, { password: pw, visitor: visitorId() }) });
  const opened = useRef(false);

  useEffect(() => {
    if (probe.data && !probe.data.requires_password && !opened.current) {
      opened.current = true;
      open.mutate(undefined);
    }
  }, [probe.data, open]);

  if (open.data) return <Viewer token={token} shared={open.data} />;
  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-surface px-4">
      {probe.isError ? (
        <ErrorState title="This link does not work" message={errorText(probe.error)} />
      ) : probe.data?.requires_password ? (
        <form
          className="flex w-full max-w-[380px] flex-col gap-4 rounded-card border border-line bg-bg p-6"
          onSubmit={(e) => {
            e.preventDefault();
            if (password) open.mutate(password);
          }}
        >
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-[10px] bg-action-soft text-action">
              <Lock size={20} />
            </span>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[17px] font-bold text-ink">{probe.data.title}</span>
              <span className="text-[13px] text-body">This deck needs a password.</span>
            </div>
          </div>
          <input
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-label="Password"
            placeholder="Password"
            className="h-10 rounded-control border border-line-strong px-3 text-[15px] text-ink focus:border-action"
          />
          <InlineError>{open.isError ? errorText(open.error) : null}</InlineError>
          <Button type="submit" variant="primary" size="lg" disabled={!password} busy={open.isPending}>
            Open the deck
          </Button>
        </form>
      ) : open.isError ? (
        <ErrorState title="This deck could not be opened" message={errorText(open.error)} />
      ) : (
        <LoadingState label="Opening the deck" />
      )}
    </div>
  );
}
