"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, BarChart3, FileText, Filter, ListChecks, Plus, Presentation, Table2, Trash2, TrendingUp, X } from "lucide-react";
import { Suspense, useMemo, useState, type ReactNode } from "react";
import { AppShell } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { Button, Card, EmptyState, ErrorState, LinkButton, PageHeader, Pill, ProgressBar, SelectChip, Spinner, type Tone } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { cx, greeting, plural, timeAgo } from "@/lib/format";
import { deckHref, useDecks, useRender } from "@/lib/hooks";
import { STARTERS, type StarterKey } from "@/lib/starters";
import type { DeckStatus, DeckSummary } from "@/lib/types";

const STARTER_ICONS: Record<StarterKey, ReactNode> = {
  notes: <FileText size={20} />,
  report: <ListChecks size={20} />,
  pitch: <TrendingUp size={20} />,
  update: <BarChart3 size={20} />,
  numbers: <Table2 size={20} />,
};

const STATUS: Record<DeckStatus, { label: string; tone: Tone }> = {
  interview: { label: "Questions for you", tone: "warn" },
  draft: { label: "Drafting outline", tone: "ai" },
  outline_ready: { label: "Outline needs you", tone: "warn" },
  building: { label: "Building", tone: "action" },
  ready: { label: "Ready", tone: "pass" },
  failed: { label: "Stopped", tone: "fail" },
};

function Thumb({ deck }: { deck: DeckSummary }) {
  const render = useRender(deck.id, deck.status === "ready");
  const first = render.data?.[0];
  if (deck.status === "ready" && first) return <SlideCanvas slide={first} />;

  if (deck.status === "building") {
    const { ready, total } = deck.progress;
    return (
      <div className="flex aspect-video flex-col justify-between bg-surface p-4">
        <span className="flex items-center gap-2 text-[12px] font-bold leading-4 text-action">
          <Spinner size={14} /> Building now
        </span>
        <div className="flex flex-col gap-2">
          <span className="text-[24px] font-bold leading-7 text-ink">
            {ready} of {total} slides
          </span>
          <ProgressBar value={total ? (ready / total) * 100 : 0} tone="action" />
        </div>
      </div>
    );
  }
  return (
    <div className="flex aspect-video flex-col justify-between bg-surface p-4">
      <span className="h-1.5 w-8 rounded-pill bg-action" />
      <span className="line-clamp-3 text-[22px] font-bold leading-[26px] text-ink">
        {deck.status === "draft" ? "The Strategist is drafting the outline" : deck.title || "Untitled deck"}
      </span>
    </div>
  );
}

function DeckCard({ deck }: { deck: DeckSummary }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteDeck(deck.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.decks }),
  });
  const status = STATUS[deck.status];
  const meta =
    deck.status === "building"
      ? `${plural(deck.slide_count, "slide")} · started ${timeAgo(deck.updated_at)}`
      : `${deck.slide_count ? plural(deck.slide_count, "slide") : "No slides yet"} · edited ${timeAgo(deck.updated_at)}`;

  return (
    <div className="group relative flex flex-col gap-2.5">
      <Link href={deckHref(deck.id, deck.status)} className="block overflow-hidden rounded-card border border-line hover:border-line-strong">
        <Thumb deck={deck} />
      </Link>
      <div className="flex flex-col gap-1.5">
        <Link href={deckHref(deck.id, deck.status)} className="truncate text-[15px] font-bold leading-5 text-ink hover:underline">
          {deck.title || "Untitled deck"}
        </Link>
        <div className="flex items-center gap-2">
          <Pill tone={status.tone}>{status.label}</Pill>
          <span className="truncate text-[13px] leading-4 text-body">{meta}</span>
        </div>
        {remove.isError ? <span className="text-[13px] text-fail">{errorText(remove.error)}</span> : null}
      </div>

      {confirming ? (
        <div className="absolute inset-x-2 top-2 flex items-center gap-2 rounded-control border border-line bg-bg p-2 text-[13px]">
          <span className="grow font-bold text-ink">Delete this deck?</span>
          <Button size="sm" variant="ink" busy={remove.isPending} onClick={() => remove.mutate()}>
            Delete
          </Button>
          <button type="button" aria-label="Keep the deck" className="flex size-[30px] items-center justify-center rounded-control hover:bg-surface-2" onClick={() => setConfirming(false)}>
            <X size={16} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          aria-label={`Delete ${deck.title || "deck"}`}
          onClick={() => setConfirming(true)}
          className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-control border border-line bg-bg text-body opacity-0 hover:text-fail focus-visible:opacity-100 group-hover:opacity-100"
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  );
}

const FILTERS = [
  { value: "all", label: "All statuses" },
  { value: "needs-you", label: "Needs you" },
  { value: "building", label: "Building" },
  { value: "ready", label: "Ready" },
];

function HomeBody() {
  const params = useSearchParams();
  const router = useRouter();
  const decks = useDecks();
  const q = (params.get("q") ?? "").trim().toLowerCase();
  const show = params.get("show") ?? "all";
  const [sort, setSort] = useState<"edited" | "title">("edited");

  const list = useMemo(() => {
    let rows = decks.data ?? [];
    if (q) rows = rows.filter((d) => d.title.toLowerCase().includes(q));
    if (show === "needs-you") rows = rows.filter((d) => d.status === "outline_ready" || d.status === "failed");
    else if (show === "building") rows = rows.filter((d) => d.status === "building" || d.status === "draft");
    else if (show === "ready") rows = rows.filter((d) => d.status === "ready");
    return [...rows].sort((a, b) => (sort === "title" ? a.title.localeCompare(b.title) : b.updated_at.localeCompare(a.updated_at)));
  }, [decks.data, q, show, sort]);

  const setShow = (value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value === "all") next.delete("show");
    else next.set("show", value);
    router.replace(next.size ? `/?${next}` : "/");
  };

  const total = decks.data?.length ?? 0;
  const today = new Date();
  const filtered = Boolean(q) || show !== "all";

  return (
    <>
      <PageHeader
        icon={<Presentation size={22} />}
        title={`${greeting(today.getHours())}. What needs saying?`}
        subtitle={today.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}
      />

      <section className="flex flex-col gap-2.5" aria-label="Start from">
        <div className="label">Start from</div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {STARTERS.map((s) => (
            <Link key={s.key} href={`/new?start=${s.key}`} className="flex items-center gap-3 rounded-card border border-line bg-bg p-3.5 hover:border-line-strong hover:bg-surface">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-action-soft text-action">{STARTER_ICONS[s.key]}</span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-[14px] font-bold leading-[18px] text-ink">{s.title}</span>
                <span className="truncate text-[13px] leading-[18px] text-body">{s.hint}</span>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4" aria-label="Decks">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-[18px] font-bold leading-6 text-ink">{q ? `Decks matching “${params.get("q")}”` : "Recent decks"}</h2>
          {decks.data ? <span className="text-[13px] text-body">{filtered ? `${list.length} of ${total}` : plural(total, "deck")}</span> : null}
          <div className="ml-auto flex items-center gap-2">
            <SelectChip icon={<Filter size={15} />} ariaLabel="Show decks by status" value={show} onChange={setShow} options={FILTERS} className="h-[30px] text-[13px]" />
            <Button size="sm" onClick={() => setSort(sort === "edited" ? "title" : "edited")} aria-label="Change sort order">
              <ArrowUpDown size={15} /> {sort === "edited" ? "Last edited" : "Title"}
            </Button>
          </div>
        </div>

        {decks.isPending ? (
          <div className="grid grid-cols-2 gap-x-6 gap-y-7 lg:grid-cols-3 2xl:grid-cols-4" role="status" aria-label="Loading your decks">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-2.5">
                <div className="pulse aspect-video rounded-card bg-surface-2" />
                <div className="pulse h-4 w-2/3 rounded-chip bg-surface-2" />
                <div className="pulse h-4 w-1/2 rounded-chip bg-surface-2" />
              </div>
            ))}
          </div>
        ) : decks.isError ? (
          <ErrorState title="Your decks could not be loaded" message={errorText(decks.error)} onRetry={() => decks.refetch()} />
        ) : total === 0 ? (
          <EmptyState
            icon={<Presentation size={22} />}
            title="No decks yet"
            message="Say what you need to say in a sentence or two. Lectern drafts an outline for you to approve, then builds the slides while you watch."
          >
            <LinkButton href="/new" variant="primary">
              <Plus size={16} /> Make your first deck
            </LinkButton>
          </EmptyState>
        ) : list.length === 0 ? (
          <EmptyState title="Nothing matches" message={q && show !== "all" ? "No deck in that state has that in its title." : q ? "No deck has that in its title." : "No deck is in that state right now."}>
            <LinkButton href="/">Show all decks</LinkButton>
          </EmptyState>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-7 lg:grid-cols-3 2xl:grid-cols-4">
            {list.map((d) => (
              <DeckCard key={d.id} deck={d} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

export default function HomePage() {
  return (
    <AppShell
      crumbs={[{ label: "Home" }]}
      actions={
        <LinkButton href="/new" variant="primary" size="sm">
          <Plus size={15} /> New deck
        </LinkButton>
      }
    >
      <Suspense fallback={<Card className={cx("p-6 text-body")}>Loading</Card>}>
        <HomeBody />
      </Suspense>
    </AppShell>
  );
}
