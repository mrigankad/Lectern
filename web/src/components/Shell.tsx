"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Database, Flag, Home, Image as ImageIcon, Palette, Plug, Search, Shield, SquareTerminal, WifiOff } from "lucide-react";
import { Fragment, useState, type FormEvent, type ReactNode } from "react";
import { DeckIconPicker } from "./DeckIcon";
import { API_URL, ApiError, IS_MOCK } from "@/lib/api";
import { cx, providerName } from "@/lib/format";
import { deckHref, useDecks, useHealth } from "@/lib/hooks";
import type { DeckStatus } from "@/lib/types";

export function ProductTile({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden className="shrink-0">
      <defs>
        <linearGradient id="lectern-tile" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3B82F6" />
          <stop offset="1" stopColor="#1D4ED8" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#lectern-tile)" />
      <polygon points="14,24 50,15 50,25 14,34" fill="#FFFFFF" />
      <rect x="28" y="32" width="8" height="16" fill="#FFFFFF" />
      <rect x="19" y="48" width="26" height="5" rx="1.5" fill="#FFFFFF" />
    </svg>
  );
}

const STATUS_DOT: Record<DeckStatus, string> = {
  interview: "bg-ai",
  draft: "bg-ai",
  outline_ready: "bg-warn",
  building: "bg-action",
  ready: "bg-pass",
  failed: "bg-fail",
};

function NavRow({
  href, icon, label, active, trailing,
}: { href: string; icon: ReactNode; label: string; active?: boolean; trailing?: ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "flex h-8 shrink-0 items-center gap-2.5 rounded-control px-2.5 text-[13px] leading-4 text-ink",
        active ? "bg-bg font-bold shadow-[0_0_0_1px_var(--line)]" : "hover:bg-surface-2",
      )}
    >
      <span className="flex w-4 shrink-0 justify-center text-body">{icon}</span>
      <span className="min-w-0 grow truncate">{label}</span>
      {trailing}
    </Link>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="label px-2.5 pb-1.5 pt-4">{children}</div>;
}

function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const decks = useDecks();
  const health = useHealth();
  const [q, setQ] = useState("");

  const list = decks.data ?? [];
  const deckMatch = pathname.match(/^\/decks\/([^/]+)/);
  const needsYou = list.filter((d) => d.status === "interview" || d.status === "outline_ready" || d.status === "failed").length;
  const recent = [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 6);

  function search(e: FormEvent) {
    e.preventDefault();
    router.push(q.trim() ? `/?q=${encodeURIComponent(q.trim())}` : "/");
  }

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-line bg-surface px-2.5 pb-3 pt-3.5">
      <Link href="/" className="flex items-center gap-[9px] px-1.5 pb-3.5 pt-0.5">
        <ProductTile />
        <span className="text-[16px] font-bold leading-5 text-ink">Lectern</span>
      </Link>

      <form onSubmit={search} role="search" className="flex h-8 shrink-0 items-center gap-2 rounded-control border border-line bg-bg px-2.5 focus-within:border-line-strong">
        <Search size={14} className="shrink-0 text-muted" aria-hidden />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search decks"
          aria-label="Search decks"
          className="min-w-0 grow bg-transparent text-[13px] leading-4 text-ink placeholder:text-muted"
        />
      </form>

      <nav className="flex min-h-0 grow flex-col gap-px overflow-y-auto pt-3" aria-label="Main">
        <NavRow href="/" icon={<Home size={16} />} label="Home" active={pathname === "/"} />
        <NavRow
          href="/?show=needs-you"
          icon={<Flag size={16} />}
          label="Needs you"
          trailing={
            needsYou > 0 ? (
              <span className="rounded-pill bg-warn-soft px-1.5 py-px text-[11px] font-bold leading-[14px] text-warn">{needsYou}</span>
            ) : null
          }
        />

        <SectionLabel>Decks</SectionLabel>
        {decks.isPending ? (
          <div className="px-2.5 py-1.5 text-[13px] text-muted">Loading decks</div>
        ) : recent.length === 0 ? (
          <div className="px-2.5 py-1.5 text-[13px] leading-[18px] text-muted">
            {decks.isError ? "Decks could not be loaded." : "Your decks will show up here."}
          </div>
        ) : (
          recent.map((d) => {
            const active = pathname.startsWith(`/decks/${d.id}`);
            return (
              <div
                key={d.id}
                className={cx(
                  "flex h-8 shrink-0 items-center gap-2 rounded-control pl-1.5 pr-2.5 text-[13px] leading-4 text-ink",
                  active ? "bg-bg font-bold shadow-[0_0_0_1px_var(--line)]" : "hover:bg-surface-2",
                )}
              >
                <span className="relative flex shrink-0">
                  <DeckIconPicker deck={d} />
                  <span
                    aria-hidden
                    className={cx("pointer-events-none absolute -bottom-0.5 -right-0.5 size-[7px] rounded-pill ring-2 ring-surface", STATUS_DOT[d.status])}
                  />
                </span>
                <Link
                  href={deckHref(d.id, d.status)}
                  aria-current={active ? "page" : undefined}
                  className="flex min-w-0 grow items-center gap-2 self-stretch"
                >
                  <span className="min-w-0 grow truncate">{d.title || "Untitled deck"}</span>
                  <span className="text-[11px] font-normal leading-[14px] text-muted">{d.slide_count || ""}</span>
                </Link>
              </div>
            );
          })
        )}

        <SectionLabel>Library</SectionLabel>
        <NavRow href="/brand-kits" icon={<Palette size={16} />} label="Brand kits" active={pathname.startsWith("/brand-kits")} />
        <NavRow
          href={deckMatch ? `/decks/${deckMatch[1]}/media` : "/media"}
          icon={<ImageIcon size={16} />}
          label="Media"
          active={pathname === "/media" || pathname.endsWith("/media")}
        />
        <NavRow href="/sources" icon={<Database size={16} />} label="Data sources" active={pathname === "/sources" || /^\/decks\/[^/]+\/data/.test(pathname)} />

        <SectionLabel>Settings</SectionLabel>
        <NavRow href="/connections" icon={<Plug size={16} />} label="Connections and models" active={pathname === "/connections"} />
        <NavRow href="/developers" icon={<SquareTerminal size={16} />} label="Claude Code and agents" active={pathname === "/developers"} />
        <NavRow href="/rules" icon={<Shield size={16} />} label="Rules" active={pathname === "/rules"} />
      </nav>

      <div className="flex flex-col gap-2 pt-2">
        <Link href="/connections" className="flex flex-col gap-1 rounded-control border border-line bg-bg p-2.5 hover:border-line-strong">
          <span className="text-[12px] leading-4 text-ink">Model in use</span>
          <span className="flex justify-between gap-2 text-[12px] leading-4">
            <span className="text-body">All agents</span>
            <span className="truncate font-bold text-ink">
              {health.data ? (health.data.provider === "offline" ? "Offline, built in" : providerName(health.data.provider)) : health.isError ? "Not reachable" : "Checking"}
            </span>
          </span>
        </Link>
        <div className="flex items-center gap-2.5 border-t border-line px-2 pb-1.5 pt-2.5">
          <div className="flex size-[26px] shrink-0 items-center justify-center rounded-pill bg-ink text-[11px] font-bold leading-[14px] text-white">L</div>
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-[13px] font-bold leading-4 text-ink">Local workspace</span>
            <span className="truncate text-[11px] leading-[14px] text-muted">{IS_MOCK ? "Mock data, nothing is saved" : "No account needed"}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

/** Shown on every screen when the API does not answer. */
function ApiBanner() {
  const health = useHealth();
  if (!health.isError) return null;
  const unreachable = health.error instanceof ApiError ? health.error.unreachable : true;
  return (
    <div role="alert" className="flex shrink-0 items-start gap-3 border-b border-line bg-fail-soft px-6 py-2.5 text-[13px] leading-[19px] text-ink">
      <WifiOff size={16} className="mt-0.5 shrink-0 text-fail" aria-hidden />
      <div>
        <span className="font-bold">
          {unreachable ? `Lectern can't reach its server at ${API_URL || "this address"}.` : "The Lectern server answered with an error."}
        </span>{" "}
        {IS_MOCK ? (
          <>The mock API should be running with the app. Restart it with <b>pnpm dev:mock</b>.</>
        ) : (
          <>
            Start it in another terminal: <b>cd server</b>, then <b>uv run uvicorn lectern.main:app --port 8000</b>. This page will reconnect by itself.
            To look around without the server, stop the app and run <b>pnpm dev:mock</b>.
          </>
        )}
      </div>
    </div>
  );
}

export type Crumb = { label: string; href?: string };

export function AppShell({
  crumbs, chip, actions, children, flush = false,
}: {
  crumbs: Crumb[];
  /** Context chip on the right of the top bar, e.g. the step. */
  chip?: ReactNode;
  /** Buttons on the right of the top bar. */
  actions?: ReactNode;
  children: ReactNode;
  /** The page lays out and scrolls its own content (editor-style screens). */
  flush?: boolean;
}) {
  return (
    <div className="flex h-dvh min-h-[560px] w-full overflow-hidden bg-bg">
      <Sidebar />
      <div className="flex min-w-0 grow basis-0 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-6">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px] leading-4 text-body">
            {crumbs.map((c, i) => (
              <Fragment key={`${c.label}-${i}`}>
                {i > 0 ? <span className="text-muted">/</span> : null}
                {c.href ? (
                  <Link href={c.href} className="shrink-0 hover:text-ink">
                    {c.label}
                  </Link>
                ) : (
                  <span className={cx("truncate", i === crumbs.length - 1 && crumbs.length > 1 && "text-ink")}>{c.label}</span>
                )}
              </Fragment>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2.5">
            {chip}
            {actions}
          </div>
        </header>
        <ApiBanner />
        {flush ? (
          <div className="flex min-h-0 grow basis-0">{children}</div>
        ) : (
          <main className="min-h-0 grow basis-0 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-10 pb-10 pt-7">{children}</div>
          </main>
        )}
      </div>
    </div>
  );
}

/** "Step 3 of 7 · Approve outline" chip for the deck flow. */
const STEPS = ["Say it", "Answer questions", "Approve outline", "Watch it build", "Refine", "Review", "Ship"] as const;
export function StepChip({ step }: { step: 1 | 2 | 3 | 4 | 5 | 6 | 7 }) {
  return (
    <span className="hidden items-center gap-2 rounded-pill bg-surface-2 px-2.5 py-[3px] text-[12px] leading-4 text-body lg:inline-flex">
      <span className="flex items-center gap-[3px]" aria-hidden>
        {STEPS.map((_, i) => (
          <span key={i} className={cx("h-1 rounded-pill", i + 1 === step ? "w-4 bg-[image:var(--action-gradient)]" : i + 1 < step ? "w-2 bg-action-line" : "w-2 bg-line-strong")} />
        ))}
      </span>
      Step {step} of {STEPS.length} · {STEPS[step - 1]}
    </span>
  );
}
