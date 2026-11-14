"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, FileText, Palette, Plus, Presentation, Trash2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { AppShell } from "@/components/Shell";
import { Button, Card, Dropdown, ErrorState, InlineError, LoadingState, PageHeader, Pill, ProgressBar } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { plural } from "@/lib/format";
import type { BrandKit, BrandRule } from "@/lib/types";

const SOURCE: Record<BrandRule["source"], string> = {
  auto: "Suggested from the template",
  guide: "From the brand guide",
  user: "Added by you",
};

function Switch({ on, onChange, label, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`flex h-6 w-10 shrink-0 items-center rounded-pill p-0.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-action focus-visible:ring-offset-2 disabled:opacity-50 ${on ? "bg-action" : "bg-line-strong"}`}
    >
      <span className={`size-5 rounded-pill bg-white transition-transform ${on ? "translate-x-4" : ""}`} />
    </button>
  );
}

function FilesCard({ kit, onUpload, busy }: { kit: BrandKit; onUpload: (kind: "template" | "guide", file: File) => void; busy: boolean }) {
  const guideInput = useRef<HTMLInputElement>(null);
  const files = [
    kit.template_file && {
      icon: Presentation, name: kit.template_file, url: `/api/brand-kits/${kit.id}/files/${kit.template_file}`,
      detail: `PowerPoint template · ${plural(kit.layouts.length, "layout")}, ${plural(Object.keys(kit.fonts).length, "font")}, ${plural(kit.palette.filter((p) => p.slot).length, "colour")}`,
    },
    kit.guide_file && {
      icon: FileText, name: kit.guide_file, url: `/api/brand-kits/${kit.id}/files/${kit.guide_file}`,
      detail: `Brand guide · ${plural(kit.rules.filter((r) => r.source === "guide").length, "rule")} found`,
    },
  ].filter(Boolean) as { icon: typeof Presentation; name: string; url: string; detail: string }[];
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3.5">
        <h2 className="text-[17px] font-bold leading-6 text-ink">Uploaded files</h2>
        <span className="text-[13px] text-body">{plural(files.length, "file")}</span>
      </div>
      {files.map(({ icon: Icon, name, url, detail }) => (
        <div key={name} className="flex gap-3 border-t border-line px-4 py-3.5">
          <Icon size={18} className="mt-0.5 shrink-0 text-ink" aria-hidden />
          <div className="flex min-w-0 flex-col gap-1">
            <a href={url} className="truncate text-[15px] font-bold leading-5 text-ink hover:underline">{name}</a>
            <span className="text-[13px] leading-[18px] text-body">{detail}</span>
            <span className="w-fit"><Pill tone="pass"><Check size={12} strokeWidth={3} /> Read successfully</Pill></span>
          </div>
        </div>
      ))}
      {!kit.guide_file ? (
        <div className="border-t border-line px-4 py-3">
          <Button size="sm" variant="ghost" busy={busy} onClick={() => guideInput.current?.click()}>
            <Plus size={15} /> Add a brand guide PDF
          </Button>
          <input ref={guideInput} type="file" accept=".pdf" className="hidden" onChange={(e) => e.target.files?.[0] && onUpload("guide", e.target.files[0])} />
        </div>
      ) : null}
    </Card>
  );
}

function MatchCard({ kit }: { kit: BrandKit }) {
  const decks = kit.decks ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const deckId = picked ?? decks[0]?.id;
  const match = useQuery({ queryKey: [...keys.brandMatch(deckId ?? ""), kit.updated_at], queryFn: () => api.brandMatch(deckId!), enabled: Boolean(deckId) });
  if (!deckId) {
    return (
      <Card className="flex flex-col gap-1.5 p-4">
        <span className="text-[13px] text-body">Brand match</span>
        <p className="text-[14px] leading-5 text-body">No deck uses this kit yet. Pick it on the new-deck page or in a deck&apos;s Design tab.</p>
      </Card>
    );
  }
  const score = match.data?.score ?? null;
  const failing = (match.data?.rules ?? []).filter((r) => r.checkable && r.enabled && !r.passed);
  const firstFail = failing[0]?.failing[0];
  return (
    <Card className="flex flex-col gap-3 p-4">
      {decks.length > 1 ? (
        <Dropdown value={deckId} options={decks.map((d) => ({ value: d.id, label: d.title }))} onChange={setPicked} ariaLabel="Deck to check">
          <span className="truncate text-[13px] text-body">Brand match · <span className="font-bold text-ink">{decks.find((d) => d.id === deckId)?.title}</span></span>
        </Dropdown>
      ) : (
        <span className="truncate text-[13px] text-body">Brand match · {decks[0].title}</span>
      )}
      {match.isPending ? (
        <LoadingState label="Checking the deck" className="py-6" />
      ) : match.isError ? (
        <InlineError>{errorText(match.error)}</InlineError>
      ) : (
        <>
          <div className="flex items-end gap-2">
            <span className="text-[44px] font-bold leading-[44px] text-ink">{score ?? "–"}</span>
            <span className="pb-1 text-[14px] text-body">out of 100</span>
          </div>
          <ProgressBar value={score ?? 0} tone="pass" />
          <span className="text-[13px] text-body">
            {failing.length === 0 ? "Every slide follows every rule that is on." : `${plural(failing.length, "rule")} not followed everywhere.`}
          </span>
          {firstFail ? (
            <div className="flex gap-2.5 rounded-control bg-warn-soft p-3">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" aria-hidden />
              <div className="flex flex-col gap-1.5 text-[13px] leading-[18px] text-ink">
                <span>Slide {firstFail.slide_index}: {firstFail.detail}</span>
                <Link href={`/decks/${deckId}?slide=${firstFail.slide_id}`} className="font-bold text-warn underline">Open slide {firstFail.slide_index}</Link>
              </div>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function RulesCard({ kit }: { kit: BrandKit }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [adding, setAdding] = useState(false);
  const save = (next: BrandKit) => qc.setQueryData(keys.brandKit(kit.id), (old: BrandKit | undefined) => ({ ...old, ...next }));
  const toggle = useMutation({ mutationFn: (r: BrandRule) => api.patchBrandRule(kit.id, r.id, { enabled: !r.enabled }), onSuccess: save });
  const remove = useMutation({ mutationFn: (r: BrandRule) => api.deleteBrandRule(kit.id, r.id), onSuccess: save });
  const add = useMutation({
    mutationFn: () => api.addBrandRule(kit.id, text.trim()),
    onSuccess: (next) => {
      save(next);
      setText("");
      setAdding(false);
    },
  });
  const on = kit.rules.filter((r) => r.enabled).length;
  return (
    <Card className="overflow-hidden">
      <div className="flex items-start justify-between gap-2 px-4 py-3.5">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-[17px] font-bold leading-6 text-ink">What Lectern will always do</h2>
          <span className="text-[13px] text-body">Brand rules, in plain words</span>
        </div>
        <Pill tone="action">{on} of {kit.rules.length} on</Pill>
      </div>
      <ul>
        {kit.rules.map((r) => (
          <li key={r.id} className={`group flex items-center gap-3 border-t border-line px-4 py-3 ${r.enabled ? "" : "bg-surface"}`}>
            <div className="flex min-w-0 grow flex-col gap-0.5">
              <span className={`text-[14px] font-bold leading-5 ${r.enabled ? "text-ink" : "text-body"}`}>{r.text}</span>
              <span className="text-[12px] leading-4 text-body">
                {SOURCE[r.source]}
                {r.kind === "note" ? " · shown to the agents, not checked" : ""}
                {!r.enabled ? " · turned off" : ""}
              </span>
            </div>
            {r.source === "user" ? (
              <button type="button" aria-label="Delete rule" onClick={() => remove.mutate(r)} className="rounded-chip p-1 text-muted opacity-0 outline-none hover:text-fail focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-action group-hover:opacity-100">
                <Trash2 size={15} />
              </button>
            ) : null}
            <Switch on={r.enabled} onChange={() => toggle.mutate(r)} label={`${r.enabled ? "Turn off" : "Turn on"}: ${r.text}`} disabled={toggle.isPending} />
          </li>
        ))}
      </ul>
      <div className="border-t border-line px-4 py-3">
        {adding ? (
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) add.mutate();
            }}
          >
            <input
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Body text no smaller than 14 points"
              className="h-10 rounded-control border border-line-strong bg-bg px-3 text-[14px] text-ink outline-none placeholder:text-muted focus:border-action focus:ring-2 focus:ring-action-soft"
            />
            <InlineError>{add.isError ? errorText(add.error) : null}</InlineError>
            <div className="flex gap-2">
              <Button size="sm" variant="primary" type="submit" disabled={!text.trim()} busy={add.isPending}>Add rule</Button>
              <Button size="sm" variant="ghost" onClick={() => setAdding(false)}><X size={15} /> Cancel</Button>
            </div>
          </form>
        ) : (
          <button type="button" onClick={() => setAdding(true)} className="flex items-center gap-2 rounded-chip text-[14px] font-bold text-action outline-none hover:underline focus-visible:ring-2 focus-visible:ring-action">
            <Plus size={16} /> Add a rule in your own words
          </button>
        )}
      </div>
    </Card>
  );
}

function LayoutThumb({ placeholders, dark }: { placeholders: string[]; dark: boolean }) {
  const has = (k: string) => placeholders.some((p) => p.includes(k));
  const fg = dark ? "bg-white" : "bg-ink";
  return (
    <div className={`relative aspect-video w-full overflow-hidden rounded-chip border border-line ${dark ? "bg-ink" : "bg-bg"}`}>
      {has("title") || has("center") ? <span className={`absolute left-[10%] top-[22%] h-[7%] w-[45%] rounded-[1px] ${fg}`} /> : null}
      {has("subtitle") ? <span className="absolute left-[10%] top-[38%] h-[5%] w-[30%] rounded-[1px] bg-muted" /> : null}
      {placeholders.filter((p) => p === "body" || p === "object").slice(0, 2).map((p, i, all) => (
        <span key={i} className="absolute top-[42%] h-[42%] rounded-[2px] bg-surface-2" style={{ left: `${10 + i * 41}%`, width: all.length > 1 ? "37%" : "78%" }} />
      ))}
      {has("picture") ? <span className="absolute right-[8%] top-[20%] h-[60%] w-[34%] rounded-[2px] bg-line-strong" /> : null}
    </div>
  );
}

export default function BrandKitPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const kit = useQuery({ queryKey: keys.brandKit(id), queryFn: () => api.getBrandKit(id) });
  const [allLayouts, setAllLayouts] = useState(false);
  const templateInput = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: "template" | "guide"; file: File }) => api.uploadBrandFile(id, kind, file),
    onSuccess: (next) => {
      qc.setQueryData(keys.brandKit(id), (old: BrandKit | undefined) => ({ ...old, ...next }));
      qc.invalidateQueries({ queryKey: keys.brandKits });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteBrandKit(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.brandKits });
      router.push("/brand-kits");
    },
  });
  const data = kit.data;
  const logo = data?.logos.find((l) => l.primary) ?? data?.logos[0];
  const filesRead = data ? [data.template_file, data.guide_file].filter(Boolean).length : 0;
  const layouts = data ? (allLayouts ? data.layouts : data.layouts.slice(0, 8)) : [];
  const dark = data ? data.theme.colors.bg.toUpperCase() !== "#FFFFFF" && data.theme.colors.bg.toUpperCase() !== "#FFF" : false;

  return (
    <AppShell crumbs={[{ label: "Brand kits", href: "/brand-kits" }, { label: data?.name ?? "Brand kit" }]}>
      {kit.isPending ? (
        <LoadingState label="Loading the brand kit" className="py-20" />
      ) : kit.isError || !data ? (
        <ErrorState title="This brand kit could not be loaded" message={errorText(kit.error)} onRetry={() => kit.refetch()} />
      ) : (
        <>
          <PageHeader
            icon={<Palette size={22} />}
            title={data.name}
            subtitle="You uploaded these once. Lectern turned them into rules that every deck on this kit follows."
            actions={
              <>
                <Pill tone="pass">Read from {plural(filesRead, "file")}</Pill>
                <Button size="sm" busy={upload.isPending} onClick={() => templateInput.current?.click()}>
                  {upload.isPending ? null : <Upload size={15} />} Upload another template
                </Button>
                <input ref={templateInput} type="file" accept=".potx,.pptx" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate({ kind: "template", file: e.target.files[0] })} />
                <Button size="sm" variant="ghost" aria-label="Delete brand kit" busy={remove.isPending} onClick={() => window.confirm(`Delete the brand kit “${data.name}”? Decks keep their current look.`) && remove.mutate()}>
                  <Trash2 size={15} />
                </Button>
              </>
            }
          />
          <InlineError>{upload.isError ? errorText(upload.error) : remove.isError ? errorText(remove.error) : null}</InlineError>
          <div className="flex items-start gap-4">
            <div className="flex w-[264px] shrink-0 flex-col gap-4">
              <FilesCard kit={data} busy={upload.isPending} onUpload={(kind, file) => upload.mutate({ kind, file })} />
              <MatchCard kit={data} />
            </div>

            <div className="flex min-w-0 grow basis-0 flex-col gap-4">
              <Card className="grid grid-cols-2 gap-4 p-4">
                <div className="flex flex-col gap-2">
                  <h2 className="text-[17px] font-bold leading-6 text-ink">Logo</h2>
                  <div className="flex h-[88px] items-center justify-center rounded-control bg-surface">
                    {logo ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={api.mediaUrl(logo.url)} alt={`${data.name} logo`} className="max-h-14 max-w-[80%] object-contain" />
                    ) : (
                      <span className="text-[13px] text-muted">No logo in the template</span>
                    )}
                  </div>
                  <span className="text-[12px] leading-4 text-body">
                    {data.logos.length ? `${plural(data.logos.length, "picture")} found on the master and layouts. Shown top right on every slide.` : "Add a logo to the template's master to show it on every slide."}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  <h2 className="text-[17px] font-bold leading-6 text-ink">Fonts</h2>
                  <span className="text-[20px] font-bold leading-6 text-ink" style={{ fontFamily: data.fonts.heading }}>Say it in one line</span>
                  <span className="text-[12px] text-body">Headings · {data.fonts.heading ?? "Urbanist"}</span>
                  <span className="border-t border-line pt-2 text-[14px] leading-5 text-ink" style={{ fontFamily: data.fonts.body }}>Body text is set like this, with room to breathe.</span>
                  <span className="text-[12px] text-body">Body · {data.fonts.body ?? "Urbanist"}{data.theme.font !== "Urbanist" ? " (PDF uses Urbanist if the font is not installed)" : ""}</span>
                </div>
              </Card>

              <Card className="flex flex-col gap-3 p-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-[17px] font-bold leading-6 text-ink">Colours</h2>
                  <span className="text-[13px] text-body">{data.palette.length} found</span>
                </div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
                  {data.palette.map((c) => (
                    <div key={`${c.name}-${c.hex}`} className="flex items-center gap-2.5">
                      <span className="size-8 shrink-0 rounded-control border border-line" style={{ background: c.hex }} />
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate text-[14px] font-bold leading-[18px] text-ink">{c.name}</span>
                        <span className="text-[12px] leading-4 text-body">{c.hex}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="flex flex-col gap-3 p-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-[17px] font-bold leading-6 text-ink">
                    Slide layouts <span className="text-[13px] font-normal text-body">{layouts.length} of {data.layouts.length} shown</span>
                  </h2>
                  {data.layouts.length > 8 ? (
                    <button type="button" onClick={() => setAllLayouts(!allLayouts)} className="rounded-chip text-[14px] font-bold text-action outline-none hover:underline focus-visible:ring-2 focus-visible:ring-action">
                      {allLayouts ? "Show fewer" : `See all ${data.layouts.length}`}
                    </button>
                  ) : null}
                </div>
                <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                  {layouts.map((l) => (
                    <div key={l.index} className="flex flex-col gap-1.5">
                      <LayoutThumb placeholders={l.placeholders} dark={dark} />
                      <span className="truncate text-[13px] text-ink">{l.name}</span>
                    </div>
                  ))}
                </div>
                <span className="text-[12px] leading-4 text-body">The PowerPoint export is built on this template, so the file opens with these layouts and master.</span>
              </Card>
            </div>

            <div className="w-[320px] shrink-0">
              <RulesCard kit={data} />
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
