"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, Clock, Compass, Pencil, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { FlowSteps } from "@/components/FlowSteps";
import { AppShell } from "@/components/Shell";
import { AiCard, Button, ErrorState, InlineError, LoadingState, Pill } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { cx } from "@/lib/format";
import { useDeck, useDeckGate } from "@/lib/hooks";
import type { InterviewQuestion, InterviewState } from "@/lib/types";

function QuestionCard({
  q, number, busy, onAnswer, onSkip,
}: { q: InterviewQuestion; number: number; busy: boolean; onAnswer: (a: string) => void; onSkip: () => void }) {
  const [text, setText] = useState(q.answer ?? "");
  const [chip, setChip] = useState<string | null>(q.answer && q.chips.includes(q.answer) ? q.answer : null);
  const answer = text.trim() || chip || "";
  return (
    <div className="flex flex-col gap-4 rounded-card border border-action bg-bg p-5">
      <div className="flex flex-col gap-1">
        <span className="text-[13px] font-bold leading-4 text-action">Question {number}</span>
        <h2 className="text-[24px] font-bold leading-[30px] text-ink">{q.text}</h2>
        {q.hint ? <p className="text-[15px] leading-5 text-body">{q.hint}</p> : null}
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Suggested answers">
        {q.chips.map((c) => (
          <button
            key={c}
            type="button"
            aria-pressed={chip === c}
            onClick={() => {
              setChip(chip === c ? null : c);
              setText("");
            }}
            className={cx(
              "inline-flex h-9 items-center gap-1.5 rounded-control border px-3 text-[14px] font-bold leading-4",
              chip === c ? "border-action bg-action-soft text-action" : "border-line-strong bg-bg text-ink hover:bg-surface",
            )}
          >
            {chip === c ? <Check size={14} /> : null}
            {c}
          </button>
        ))}
      </div>
      <label className="flex h-11 items-center gap-2.5 rounded-control border border-line-strong px-3.5 focus-within:border-action">
        <Pencil size={14} className="shrink-0 text-muted" aria-hidden />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && answer && !busy) onAnswer(answer);
          }}
          placeholder={chip ? `${chip}. Add detail in your own words` : "Or answer in your own words"}
          aria-label="Your answer"
          className="min-w-0 grow bg-transparent text-[15px] leading-5 text-ink placeholder:text-muted"
        />
      </label>
      <div className="flex flex-wrap gap-2.5">
        <Button variant="primary" size="lg" disabled={!answer} busy={busy} onClick={() => onAnswer(answer)}>
          {number === 3 ? "Draft the outline" : "Next question"} <ArrowRight size={18} />
        </Button>
        <Button size="lg" disabled={busy} onClick={onSkip}>
          I&apos;m not sure, skip it
        </Button>
      </div>
    </div>
  );
}

function Understood({ state, onSkipAll, busy }: { state: InterviewState; onSkipAll: () => void; busy: boolean }) {
  const u = state.understood;
  const pending = (key: string) => {
    const idx = state.questions.findIndex((q) => q.key === key);
    const q = state.questions[idx];
    return q?.skipped ? "Skipped. The Strategist will choose." : `Waiting for question ${idx + 1}`;
  };
  const rows: { label: string; value?: string | null; key: string }[] = [
    { label: "Audience", value: u.audience, key: "audience" },
    { label: "Goal", value: u.goal, key: "goal" },
    { label: "Time", value: u.time ? `${u.time}${u.minutes ? ` (${u.minutes} min)` : ""}` : null, key: "minutes" },
  ];
  return (
    <AiCard className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <h2 className="text-[18px] font-bold leading-6 text-ink">What I understood</h2>
          <Pill tone="ai">AI note</Pill>
        </div>
        <span className="flex items-center gap-1.5 text-[13px] leading-4 text-body">
          <RefreshCw size={12} aria-hidden /> Fills in as you answer
        </span>
      </div>
      <div className="flex flex-col rounded-card bg-bg" aria-live="polite">
        {rows.map((r, i) => (
          <div key={r.label} className={cx("flex gap-4 px-4 py-3.5", i > 0 && "border-t border-line")}>
            <span className="w-[72px] shrink-0 text-[14px] leading-5 text-body">{r.label}</span>
            <span className={cx("min-w-0 text-[14px] leading-5", r.value ? "font-bold text-ink" : "text-muted")}>
              {r.value || pending(r.key)}
            </span>
          </div>
        ))}
      </div>
      {u.numbers.length > 0 ? (
        <div className="flex flex-col gap-2">
          <span className="text-[14px] font-bold leading-5 text-ink">Key numbers found in your prompt</span>
          <div className="grid grid-cols-3 gap-2">
            {u.numbers.map((n) => (
              <div key={`${n.value}-${n.label}`} className="flex flex-col gap-1 rounded-card bg-bg p-3">
                <span className={cx("text-[22px] font-bold leading-7", n.tone === "bad" ? "text-fail" : "text-ink")}>{n.value}</span>
                <span className="text-[12px] font-bold leading-4 text-ink">{n.label}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <Button className="w-full" disabled={busy} onClick={onSkipAll}>
        Skip questions, build the outline <ArrowRight size={16} />
      </Button>
    </AiCard>
  );
}

export default function InterviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const deck = useDeck(id);
  const redirecting = useDeckGate(deck.data, "interview");
  const interview = useQuery({ queryKey: keys.interview(id), queryFn: () => api.getInterview(id), enabled: deck.data?.status === "interview" });
  const [editing, setEditing] = useState<string | null>(null);

  const after = (state: InterviewState) => {
    qc.setQueryData(keys.interview(id), state);
    setEditing(null);
    if (state.status === "done") {
      qc.invalidateQueries({ queryKey: keys.deck(id) });
      qc.invalidateQueries({ queryKey: keys.decks });
    }
  };
  const answer = useMutation({ mutationFn: (v: { q: string; a: string }) => api.answerInterview(id, v.q, v.a), onSuccess: after });
  const skip = useMutation({ mutationFn: (v: { q?: string; all?: boolean }) => api.skipInterview(id, { questionId: v.q, all: v.all }), onSuccess: after });
  const busy = answer.isPending || skip.isPending;

  const state = interview.data;
  const activeId = editing ?? state?.current ?? null;
  useEffect(() => setEditing(null), [state?.status]);
  const answered = state ? state.questions.filter((q) => q.answer || q.skipped).length : 0;

  return (
    <AppShell crumbs={[{ label: "Home", href: "/" }, { label: deck.data?.title || "Deck" }, { label: "Questions" }]} flush>
      <div className="flex min-w-0 grow flex-col overflow-y-auto">
        <FlowSteps current={2} />
        <div className="mx-auto flex w-full max-w-[1280px] gap-6 px-10 pb-10 pt-7">
          {deck.isError ? (
            <ErrorState title="This deck could not be opened" message={errorText(deck.error)} />
          ) : !state || redirecting ? (
            interview.isError ? (
              <ErrorState title="The questions could not be loaded" message={errorText(interview.error)} />
            ) : (
              <LoadingState label={redirecting ? "Opening the outline" : "The Strategist is reading your prompt"} />
            )
          ) : (
            <>
              <div className="flex min-w-0 grow basis-0 flex-col gap-4">
                <div className="flex items-center gap-3.5">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-teal-soft text-teal">
                    <Compass size={22} />
                  </div>
                  <div className="flex min-w-0 grow flex-col">
                    <h1 className="text-[28px] font-bold leading-8 text-ink">Strategist</h1>
                    <p className="text-[15px] leading-5 text-body">Three short questions, then I draft the outline.</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 text-[13px] font-bold text-ink">
                    Question {Math.min(answered + 1, state.questions.length)} of {state.questions.length}
                    <span className="flex gap-1" aria-hidden>
                      {state.questions.map((q) => (
                        <span key={q.id} className={cx("h-1 w-8 rounded-pill", q.answer || q.skipped || q.id === activeId ? "bg-action" : "bg-line-strong")} />
                      ))}
                    </span>
                  </div>
                </div>

                {state.questions.map((q, i) => {
                  if (q.id === activeId && state.status === "open") {
                    return (
                      <QuestionCard
                        key={q.id}
                        q={q}
                        number={i + 1}
                        busy={busy}
                        onAnswer={(a) => answer.mutate({ q: q.id, a })}
                        onSkip={() => skip.mutate({ q: q.id })}
                      />
                    );
                  }
                  const done = Boolean(q.answer || q.skipped);
                  return (
                    <div key={q.id} className={cx("flex items-center gap-3.5 rounded-card border border-line px-4 py-3.5", done ? "bg-bg" : "bg-surface")}>
                      <span className={cx("flex size-7 shrink-0 items-center justify-center rounded-pill", done ? "bg-pass-soft text-pass" : "text-muted")}>
                        {done ? <Check size={14} /> : <Clock size={16} />}
                      </span>
                      <div className="flex min-w-0 grow flex-col">
                        <span className={cx("text-[13px] leading-4", done ? "text-body" : "text-[15px] font-bold text-body")}>
                          {i + 1} · {q.text}{q.from_brief ? " · from your brief" : ""}
                        </span>
                        {done ? (
                          <span className="truncate text-[15px] font-bold leading-5 text-ink">{q.answer || "Skipped"}</span>
                        ) : null}
                      </div>
                      {done && state.status === "open" ? (
                        <Button size="sm" onClick={() => setEditing(q.id)}>
                          <Pencil size={13} /> Change
                        </Button>
                      ) : !done ? (
                        <Pill>Up next</Pill>
                      ) : null}
                    </div>
                  );
                })}
                <InlineError>{answer.isError ? errorText(answer.error) : skip.isError ? errorText(skip.error) : null}</InlineError>
                {state.status === "done" ? <LoadingState label="Drafting the outline from your answers" /> : null}
              </div>
              <div className="w-[392px] shrink-0">
                <Understood state={state} busy={busy || state.status === "done"} onSkipAll={() => skip.mutate({ all: true })} />
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
