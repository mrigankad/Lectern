"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Clock, Copy, Download, ExternalLink, Globe, Link2, Lock, Send, StickyNote } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { AppShell, StepChip } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { Button, Card, Dropdown, ErrorState, InlineError, LinkButton, LoadingState, PageHeader, Pill } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { cx } from "@/lib/format";
import { useDeck, useRender } from "@/lib/hooks";
import type { ShareAccess, ShareLink, ShareSettings } from "@/lib/types";

function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx("flex h-6 w-11 shrink-0 items-center rounded-pill p-0.5 transition-colors disabled:opacity-50", checked ? "justify-end bg-action" : "justify-start bg-line-strong")}
    >
      <span className="size-5 rounded-pill bg-white" />
    </button>
  );
}

function Row({ icon, children, trailing, className }: { icon: ReactNode; children: ReactNode; trailing?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex items-center gap-3 border-t border-line px-4 py-3.5", className)}>
      <span className="flex w-5 shrink-0 justify-center text-ink">{icon}</span>
      <div className="min-w-0 grow">{children}</div>
      {trailing}
    </div>
  );
}

function duration(seconds: number) {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  return `${Math.round(seconds / 60)} min`;
}

const EXPIRY = [
  { value: "0", label: "Never" },
  { value: "1", label: "In 1 day" },
  { value: "7", label: "In 7 days" },
  { value: "30", label: "In 30 days" },
  { value: "90", label: "In 90 days" },
];

function Settings({ id, link }: { id: string; link: ShareLink }) {
  const qc = useQueryClient();
  const [password, setPassword] = useState("");
  const [wantPassword, setWantPassword] = useState(link.access === "password");
  const [expiry, setExpiry] = useState(link.expires_at ? "current" : "0");
  const update = useMutation({
    mutationFn: (body: ShareSettings) => api.updateShare(id, link.id, body),
    onSuccess: (next) => {
      qc.setQueryData<ShareLink[]>(keys.shares(id), (old) => (old ?? []).map((l) => (l.id === next.id ? next : l)));
      setPassword("");
    },
  });
  useEffect(() => setWantPassword(link.access === "password"), [link.access]);

  const access = (a: ShareAccess) => {
    if (a === "anyone") {
      setWantPassword(false);
      update.mutate({ access: "anyone" });
    } else if (link.has_password) {
      setWantPassword(true);
      update.mutate({ access: "password" });
    } else setWantPassword(true);
  };
  const expiryOptions = link.expires_at
    ? [{ value: "current", label: `On ${new Date(link.expires_at).toLocaleDateString()}` }, ...EXPIRY]
    : EXPIRY;

  const choice = (value: ShareAccess, icon: ReactNode, title: string, hint: string) => {
    const on = (value === "password") === wantPassword;
    return (
      <button
        type="button"
        role="radio"
        aria-checked={on}
        onClick={() => access(value)}
        className={cx("flex w-full items-center gap-3 border-t border-line px-4 py-3 text-left", on ? "bg-action-soft" : "hover:bg-surface")}
      >
        <span className={cx("flex w-5 shrink-0 justify-center", on ? "text-action" : "text-ink")}>{icon}</span>
        <span className="flex min-w-0 grow flex-col">
          <span className="text-[15px] font-bold leading-5 text-ink">{title}</span>
          <span className="text-[13px] leading-4 text-body">{hint}</span>
        </span>
        <span className={cx("flex size-[18px] shrink-0 items-center justify-center rounded-pill border-2", on ? "border-action" : "border-line-strong")}>
          {on ? <span className="size-2 rounded-pill bg-action" /> : null}
        </span>
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <Card className="overflow-hidden">
        <div className="bg-surface px-4 py-3 text-[13px] leading-4 text-body">Who can open it</div>
        <div role="radiogroup" aria-label="Who can open it">
          {choice("anyone", <Globe size={18} />, "Anyone with the link", "No sign-in needed")}
          {choice("password", <Lock size={18} />, "Password", "Anyone who knows the password")}
        </div>
        {wantPassword ? (
          <form
            className="flex gap-2 border-t border-line px-4 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (password.trim()) update.mutate({ access: "password", password: password.trim() });
            }}
          >
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={link.has_password ? "Set a new password" : "Choose a password"}
              aria-label="Password"
              className="h-9 min-w-0 grow rounded-control border border-line-strong px-3 text-[14px] text-ink focus:border-action"
            />
            <Button type="submit" size="md" variant="primary" disabled={!password.trim()} busy={update.isPending}>
              {link.has_password ? "Change" : "Set"}
            </Button>
          </form>
        ) : null}
      </Card>

      <Card className="overflow-hidden">
        <div className="bg-surface px-4 py-3 text-[13px] leading-4 text-body">Link settings</div>
        <Row icon={<Download size={18} />} trailing={<Switch label="Allow download" checked={link.allow_download} onChange={(v) => update.mutate({ allow_download: v })} />}>
          <span className="text-[15px] leading-5 text-ink">Allow download</span>
        </Row>
        <Row icon={<StickyNote size={18} />} trailing={<Switch label="Show speaker notes" checked={link.show_notes} onChange={(v) => update.mutate({ show_notes: v })} />}>
          <span className="text-[15px] leading-5 text-ink">Show speaker notes</span>
        </Row>
        <Row
          icon={<Clock size={18} />}
          trailing={
            <Dropdown
              value={expiry}
              options={expiryOptions}
              ariaLabel="Link expires"
              onChange={(v) => {
                setExpiry(v);
                if (v !== "current") update.mutate({ expires_in_days: Number(v) });
              }}
            />
          }
        >
          <span className="text-[15px] leading-5 text-ink">Link expires</span>
        </Row>
      </Card>
      <InlineError>{update.isError ? errorText(update.error) : null}</InlineError>
    </div>
  );
}

export default function SharePage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const deck = useDeck(id);
  const render = useRender(id, deck.data?.status === "ready");
  const shares = useQuery({ queryKey: keys.shares(id), queryFn: () => api.listShares(id), refetchInterval: 15_000 });
  const create = useMutation({
    mutationFn: () => api.createShare(id, {}),
    onSuccess: (link) => qc.setQueryData<ShareLink[]>(keys.shares(id), (old) => [...(old ?? []), link]),
  });
  const remove = useMutation({
    mutationFn: (shareId: string) => api.deleteShare(id, shareId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.shares(id) }),
  });
  const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);

  const link = shares.data?.[0];
  const url = link ? `${origin}${link.path}` : "";
  const notReady = deck.data && deck.data.status !== "ready";
  const most = link?.stats.most_viewed;
  const mostRender = most ? render.data?.find((r) => r.id === most.slide_id) : undefined;
  const first = render.data?.[0];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <AppShell
      crumbs={[{ label: "Home", href: "/" }, { label: deck.data?.title || "Deck", href: `/decks/${id}` }, { label: "Share link" }]}
      chip={<StepChip step={7} />}
    >
      <PageHeader
        icon={<Send size={20} />}
        title="Share as a web link"
        subtitle={`People open your deck in a browser. No account or PowerPoint needed.${deck.data ? ` ${deck.data.slides.length} slides.` : ""}`}
        actions={
          <LinkButton href={`/decks/${id}`}>
            <ArrowLeft size={16} /> Back to deck
          </LinkButton>
        }
      />
      {deck.isError || shares.isError ? (
        <ErrorState title="Sharing could not be loaded" message={errorText(deck.error ?? shares.error)} />
      ) : !deck.data || !shares.data ? (
        <LoadingState />
      ) : !link ? (
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <span className="flex size-10 items-center justify-center rounded-[10px] bg-action-soft text-action">
            <Link2 size={20} />
          </span>
          <div className="flex min-w-0 grow flex-col">
            <span className="text-[16px] font-bold text-ink">No link yet</span>
            <span className="text-[14px] text-body">
              {notReady ? "The deck is not finished yet. People will see the slides that are ready." : "Make a link, then choose who can open it."}
            </span>
          </div>
          <Button variant="primary" size="lg" onClick={() => create.mutate()} busy={create.isPending}>
            <Link2 size={18} /> Create link
          </Button>
          <InlineError>{create.isError ? errorText(create.error) : null}</InlineError>
        </Card>
      ) : (
        <>
          <Card className="flex flex-wrap items-center gap-2.5 p-4">
            <div className="flex h-11 min-w-0 grow items-center gap-3 rounded-control border border-line bg-surface px-4">
              <Link2 size={16} className="shrink-0 text-body" />
              <span className="min-w-0 grow truncate text-[16px] font-bold text-ink">{url.replace(/^https?:\/\//, "")}</span>
              {link.expired ? <Pill tone="fail">Expired</Pill> : <Pill tone="pass">Link is live</Pill>}
            </div>
            <Button variant="primary" size="lg" onClick={copy}>
              {copied ? <Check size={18} /> : <Copy size={18} />} {copied ? "Copied" : "Copy link"}
            </Button>
          </Card>

          <div className="flex flex-wrap gap-6">
            <div className="w-[320px] shrink-0">
              <Settings key={link.id} id={id} link={link} />
              <Button
                variant="ghost"
                size="sm"
                className="mt-3 text-fail"
                busy={remove.isPending}
                onClick={() => remove.mutate(link.id)}
              >
                Turn off this link
              </Button>
            </div>

            <div className="flex min-w-0 grow basis-0 flex-col gap-4">
              <Card className="flex flex-wrap gap-5 p-5">
                <div className="w-[240px] shrink-0 overflow-hidden rounded-control border border-line">
                  {first ? <SlideCanvas slide={first} /> : <div className="aspect-video bg-surface" />}
                </div>
                <div className="flex min-w-0 grow basis-0 flex-col gap-1">
                  <span className="text-[13px] text-body">What people see</span>
                  <span className="text-[17px] font-bold text-ink">{deck.data.title}</span>
                  <span className="text-[14px] leading-5 text-body">
                    A web page with all {deck.data.slides.length} slides. They click through at their own pace, on a laptop or a phone
                    {link.show_notes ? ", with your speaker notes" : ""}.
                  </span>
                  <a href={link.path} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1.5 text-[14px] font-bold text-action">
                    <ExternalLink size={14} /> Open the link as a viewer
                  </a>
                </div>
              </Card>

              <div className="grid grid-cols-2 gap-4">
                <Card className="flex flex-col gap-1 p-5">
                  <span className="text-[13px] text-body">Views so far</span>
                  <span className="flex items-baseline gap-2">
                    <span className="text-[28px] font-bold leading-8 text-ink">{link.stats.opens}</span>
                    <span className="text-[13px] text-body">
                      times opened{link.stats.visitors ? ` · ${link.stats.visitors} ${link.stats.visitors === 1 ? "person" : "people"}` : ""}
                    </span>
                  </span>
                </Card>
                <Card className="flex flex-col gap-1 p-5">
                  <span className="text-[13px] text-body">Average time</span>
                  <span className="text-[28px] font-bold leading-8 text-ink">{link.stats.opens ? duration(link.stats.avg_seconds) : "—"}</span>
                </Card>
              </div>

              <Card className="flex flex-wrap items-center gap-4 p-5">
                {most ? (
                  <>
                    <div className="w-[160px] shrink-0 overflow-hidden rounded-control border border-line">
                      {mostRender ? <SlideCanvas slide={mostRender} /> : <div className="aspect-video bg-surface" />}
                    </div>
                    <div className="flex min-w-0 grow basis-0 flex-col gap-0.5">
                      <span className="text-[13px] text-body">Most viewed slide</span>
                      <span className="text-[15px] font-bold leading-5 text-ink">
                        Slide {most.index} · {most.headline}
                      </span>
                      <span className="text-[13px] text-body">{Math.round(most.avg_seconds)} seconds on average</span>
                    </div>
                  </>
                ) : (
                  <span className="text-[14px] text-body">Once people open the link, you will see which slide holds them longest.</span>
                )}
              </Card>

              {link.stats.opens > 0 ? (
                <Card className="flex flex-col gap-2 p-5">
                  <span className="text-[14px] font-bold text-ink">Time per slide</span>
                  {link.stats.slides.map((s) => {
                    const max = Math.max(1, ...link.stats.slides.map((x) => x.seconds));
                    return (
                      <div key={s.slide_id} className="flex items-center gap-3 text-[13px]">
                        <span className="w-6 shrink-0 text-right text-muted">{s.index}</span>
                        <span className="w-[220px] shrink-0 truncate text-ink">{s.headline}</span>
                        <span className="h-2 grow overflow-hidden rounded-pill bg-surface-2">
                          <span className="block h-2 rounded-pill bg-action" style={{ width: `${(s.seconds / max) * 100}%` }} />
                        </span>
                        <span className="w-14 shrink-0 text-right text-body">{Math.round(s.avg_seconds)} s avg</span>
                      </div>
                    );
                  })}
                </Card>
              ) : null}
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
