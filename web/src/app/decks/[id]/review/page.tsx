"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, Flag, Wand2 } from "lucide-react";
import { deckProblem } from "@/components/DeckStates";
import { RulesPanel } from "@/components/RulesPanel";
import { AppShell, StepChip } from "@/components/Shell";
import { SlideCanvas, SlidePlaceholder } from "@/components/SlideCanvas";
import { Button, Card, EmptyState, ErrorState, InlineError, LinkButton, LoadingState, Pill, ProgressBar, type Tone } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { useDeckEvents } from "@/lib/events";
import { cx, plural } from "@/lib/format";
import { useDeck, useDeckGate, useRender } from "@/lib/hooks";
import type { Finding, FindingAction, Severity } from "@/lib/types";

const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  high: { label: "High", tone: "fail" },
  medium: { label: "Medium", tone: "warn" },
  low: { label: "Low", tone: "neutral" },
};

const NUMBER_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

function verdict(open: number): string {
  if (open === 0) return "Ready to ship. Nothing left to fix.";
  const n = NUMBER_WORDS[open] ?? String(open);
  return `Nearly ready. ${n} ${open === 1 ? "thing" : "things"} to fix first.`;
}

function Score({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex w-[120px] shrink-0 flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] leading-4 text-body">{label}</span>
        <span className="text-[20px] font-bold leading-6 text-ink">{Math.round(value)}</span>
      </div>
      <ProgressBar value={value} />
    </div>
  );
}

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const query = useDeck(id);
  const deck = query.data;
  const redirecting = useDeckGate(deck, "review");
  useDeckEvents(id);
  const usable = Boolean(deck) && !redirecting;
  const critic = useQuery({ queryKey: keys.critic(id), queryFn: () => api.getCritic(id), enabled: usable });
  const render = useRender(id, usable);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.critic(id) });
    qc.invalidateQueries({ queryKey: keys.deck(id) });
    qc.invalidateQueries({ queryKey: keys.render(id) });
    qc.invalidateQueries({ queryKey: keys.rules });
  };
  const act = useMutation({ mutationFn: (v: { fid: string; action: FindingAction }) => api.actOnFinding(id, v.fid, v.action), onSettled: refresh });
  const fixAll = useMutation({ mutationFn: () => api.fixAll(id), onSettled: refresh });

  const problem = deckProblem(query, redirecting);
  const findings = critic.data?.findings ?? [];
  const open = findings.filter((f) => f.status === "open").length;
  const fixed = findings.filter((f) => f.status === "fixed").length;
  const kept = findings.filter((f) => f.status === "kept").length;
  const rendered = new Map((render.data ?? []).map((r) => [r.id, r]));

  // Group findings by slide, in slide order.
  const groups: { slideId: string; index: number; items: Finding[] }[] = [];
  [...findings].sort((a, b) => a.slide_index - b.slide_index).forEach((f) => {
    const last = groups[groups.length - 1];
    if (last && last.slideId === f.slide_id) last.items.push(f);
    else groups.push({ slideId: f.slide_id, index: f.slide_index, items: [f] });
  });
  const busyId = act.isPending ? act.variables?.fid : null;

  return (
    <AppShell
      crumbs={[{ label: "Home", href: "/" }, { label: deck?.title || "Deck", href: `/decks/${id}` }, { label: "Critic report" }]}
      chip={<StepChip step={6} />}
      actions={
        <LinkButton href={`/decks/${id}`} size="sm">
          <ArrowLeft size={15} /> Back to editing
        </LinkButton>
      }
    >
      {problem ??
        (critic.isPending ? (
          <LoadingState label="The Critic is reading every slide" />
        ) : critic.isError ? (
          <ErrorState title="The Critic report could not be loaded" message={errorText(critic.error)} onRetry={() => critic.refetch()} />
        ) : (
          <div className="flex items-start gap-4">
            <div className="flex min-w-0 grow basis-0 flex-col gap-4">
              <Card className="flex flex-wrap items-end justify-between gap-6 p-5">
                <div className="flex items-end gap-5">
                  <div className="flex items-end gap-2">
                    <span className="text-[88px] font-bold leading-[76px] tracking-[-0.04em] text-ink">{Math.round(critic.data.score)}</span>
                    <span className="pb-1 text-[14px] text-body">out of 100</span>
                  </div>
                  <div className="flex flex-col gap-1 pb-0.5">
                    <span className="text-[12px] leading-4 text-body">The Critic read all {plural(deck?.slides.length ?? 0, "slide")}</span>
                    <h1 className="max-w-[300px] text-[22px] font-bold leading-[26px] text-ink">{verdict(open)}</h1>
                  </div>
                </div>
                <div className="flex gap-6">
                  <Score label="Story" value={critic.data.story} />
                  <Score label="Design" value={critic.data.design} />
                  <Score label="Editability" value={critic.data.editability} />
                </div>
              </Card>

              <Card className="overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <div className="flex items-baseline gap-3">
                    <h2 className="text-[15px] font-bold leading-5 text-ink">{plural(findings.length, "finding")}</h2>
                    <span className="text-[13px] text-body">
                      {open} open · {fixed} fixed · {kept} kept on purpose
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <LinkButton href={`/decks/${id}/export`} size="sm" variant={open === 0 ? "primary" : "secondary"}>
                      Continue to export <ArrowRight size={15} />
                    </LinkButton>
                    {open > 0 ? (
                      <Button size="sm" variant="primary" busy={fixAll.isPending} onClick={() => fixAll.mutate()}>
                        <Wand2 size={15} /> Fix all {open}
                      </Button>
                    ) : null}
                  </div>
                </div>
                {act.isError || fixAll.isError ? (
                  <div className="border-t border-line px-4 py-2.5">
                    <InlineError>{errorText(act.error ?? fixAll.error)}</InlineError>
                  </div>
                ) : null}

                {findings.length === 0 ? (
                  <div className="border-t border-line p-4">
                    <EmptyState icon={<Check size={22} />} title="The Critic found nothing to fix" message="No overflow, no small text, no long lists, and every slide has notes." className="border-none py-8" />
                  </div>
                ) : (
                  groups.map((g) => {
                    const r = rendered.get(g.slideId);
                    const headline = deck?.slides.find((s) => s.id === g.slideId)?.headline;
                    return (
                      <div key={g.slideId} className="flex gap-4 border-t border-line px-4 py-3.5">
                        <Link href={`/decks/${id}?slide=${g.slideId}`} title="Open this slide" className="h-fit shrink-0 overflow-hidden rounded-chip border border-line-strong hover:border-action">
                          {r ? <SlideCanvas slide={r} width={128} /> : <SlidePlaceholder width={128} label={String(g.index)} />}
                        </Link>
                        <div className="flex min-w-0 grow flex-col">
                          <div className="truncate pb-1.5 text-[12px] leading-4 text-body">
                            Slide {g.index}
                            {headline ? ` · ${headline}` : ""}
                          </div>
                          {g.items.map((f, i) => {
                            const settled = f.status !== "open";
                            const busy = busyId === f.id || fixAll.isPending;
                            return (
                              <div key={f.id} className={cx("flex flex-wrap items-center gap-x-4 gap-y-2", i > 0 && "mt-3 border-t border-line pt-3")}>
                                <div className="flex min-w-[240px] grow basis-0 flex-col gap-0.5">
                                  <span className={cx("text-[15px] font-bold leading-5", settled ? "text-body" : "text-ink")}>{f.title}</span>
                                  <span className="text-[13px] leading-[19px] text-body">{f.detail}</span>
                                </div>
                                <Pill tone={settled ? "neutral" : SEVERITY[f.severity]?.tone ?? "neutral"}>{SEVERITY[f.severity]?.label ?? f.severity}</Pill>
                                <div className="flex w-[292px] shrink-0 items-center justify-end gap-2">
                                  {f.status === "open" ? (
                                    <>
                                      <Button size="sm" variant="primary" busy={busyId === f.id && act.variables?.action === "fix"} disabled={busy} onClick={() => act.mutate({ fid: f.id, action: "fix" })}>
                                        Fix it
                                      </Button>
                                      <Button size="sm" disabled={busy} onClick={() => act.mutate({ fid: f.id, action: "keep" })}>
                                        Keep it, this is intentional
                                      </Button>
                                    </>
                                  ) : (
                                    <>
                                      {f.status === "fixed" ? (
                                        <Pill tone="pass">
                                          <Check size={13} strokeWidth={2.5} aria-hidden /> Fixed
                                        </Pill>
                                      ) : (
                                        <Pill tone="teal">
                                          <Flag size={13} aria-hidden /> Kept on purpose
                                        </Pill>
                                      )}
                                      <button
                                        type="button"
                                        disabled={busy}
                                        onClick={() => act.mutate({ fid: f.id, action: "reopen" })}
                                        className="text-[13px] font-bold text-ink underline underline-offset-2 disabled:opacity-50"
                                      >
                                        {f.status === "fixed" ? "Reopen" : "Change"}
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })
                )}
              </Card>
            </div>
            <RulesPanel className="w-[340px] shrink-0" />
          </div>
        ))}
    </AppShell>
  );
}
