"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Palette, Presentation, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { AppShell } from "@/components/Shell";
import { Button, Card, EmptyState, ErrorState, InlineError, LoadingState, PageHeader, Pill } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { plural } from "@/lib/format";
import type { BrandKit } from "@/lib/types";

function UploadCard() {
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [template, setTemplate] = useState<File | null>(null);
  const [guide, setGuide] = useState<File | null>(null);
  const templateInput = useRef<HTMLInputElement>(null);
  const guideInput = useRef<HTMLInputElement>(null);
  const create = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("name", name);
      if (template) form.append("template", template);
      if (guide) form.append("guide", guide);
      return api.createBrandKit(form);
    },
    onSuccess: (kit) => {
      qc.invalidateQueries({ queryKey: keys.brandKits });
      router.push(`/brand-kits/${kit.id}`);
    },
  });

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-[17px] font-bold leading-6 text-ink">New brand kit</h2>
        <p className="text-[13px] leading-[19px] text-body">
          Upload your PowerPoint template once. Lectern reads its colours, fonts, logo and layouts and turns them into rules every deck follows.
        </p>
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-bold text-ink">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Taken from the template if left empty"
          className="h-10 rounded-control border border-line-strong bg-bg px-3 text-[14px] text-ink outline-none placeholder:text-muted focus:border-action focus:ring-2 focus:ring-action-soft"
        />
      </label>
      <div className="grid grid-cols-1 gap-3">
        {([
          ["template", template, templateInput, ".potx,.pptx", Presentation, "PowerPoint template", ".potx or .pptx"],
          ["guide", guide, guideInput, ".pdf", FileText, "Brand guide (optional)", "PDF: colours and rules are read from it"],
        ] as const).map(([key, file, ref, accept, Icon, title, hint]) => (
          <button
            key={key}
            type="button"
            onClick={() => ref.current?.click()}
            className="flex items-center gap-3 rounded-card border border-dashed border-line-strong p-4 text-left outline-none hover:border-action hover:bg-surface focus-visible:ring-2 focus-visible:ring-action"
          >
            <Icon size={22} className="shrink-0 text-action" aria-hidden />
            <span className="flex min-w-0 flex-col">
              <span className="break-words text-[14px] font-bold leading-5 text-ink [overflow-wrap:anywhere]">{file ? file.name : title}</span>
              <span className="text-[12px] leading-4 text-body">{file ? "Click to choose another file" : hint}</span>
            </span>
            <input
              ref={ref}
              type="file"
              accept={accept}
              className="hidden"
              onChange={(e) => (key === "template" ? setTemplate : setGuide)(e.target.files?.[0] ?? null)}
            />
          </button>
        ))}
      </div>
      <InlineError>{create.isError ? errorText(create.error) : null}</InlineError>
      <div>
        <Button variant="primary" onClick={() => create.mutate()} disabled={!template && !guide} busy={create.isPending}>
          {create.isPending ? null : <Upload size={16} />} Read the files
        </Button>
      </div>
    </Card>
  );
}

function KitCard({ kit }: { kit: BrandKit }) {
  const logo = kit.logos.find((l) => l.primary) ?? kit.logos[0];
  const enabled = kit.rules.filter((r) => r.enabled).length;
  return (
    <Link
      href={`/brand-kits/${kit.id}`}
      className="flex flex-col gap-3 rounded-card border border-line bg-bg p-4 outline-none hover:border-line-strong focus-visible:ring-2 focus-visible:ring-action"
    >
      <div className="flex h-[72px] items-center justify-center rounded-control bg-surface">
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={api.mediaUrl(logo.url)} alt={`${kit.name} logo`} className="max-h-12 max-w-[70%] object-contain" />
        ) : (
          <span className="text-[13px] text-muted">No logo found</span>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[15px] font-bold leading-5 text-ink">{kit.name}</span>
        <Pill tone="action">{plural(kit.deck_count ?? 0, "deck")}</Pill>
      </div>
      <div className="flex gap-1">
        {kit.palette.slice(0, 10).map((c) => (
          <span key={`${c.name}-${c.hex}`} title={`${c.name} ${c.hex}`} className="size-5 rounded-chip border border-line" style={{ background: c.hex }} />
        ))}
      </div>
      <span className="text-[13px] leading-[18px] text-body">
        {kit.fonts.heading || kit.fonts.body || "Urbanist"} · {plural(kit.layouts.length, "layout")} · {enabled} of {plural(kit.rules.length, "rule")} on
      </span>
    </Link>
  );
}

export default function BrandKitsPage() {
  const kits = useQuery({ queryKey: keys.brandKits, queryFn: api.listBrandKits });
  return (
    <AppShell crumbs={[{ label: "Library" }, { label: "Brand kits" }]}>
      <PageHeader icon={<Palette size={22} />} title="Brand kits" subtitle="Your templates, read once and followed on every deck." />
      <div className="flex items-start gap-4">
        <div className="flex min-w-0 grow basis-0 flex-col gap-3">
          {kits.isPending ? (
            <LoadingState label="Loading brand kits" className="py-14" />
          ) : kits.isError ? (
            <ErrorState title="Brand kits could not be loaded" message={errorText(kits.error)} onRetry={() => kits.refetch()} />
          ) : kits.data.length === 0 ? (
            <EmptyState
              icon={<Palette size={22} />}
              title="No brand kits yet"
              message="Upload a .potx or .pptx template and new decks can look like your company's own slides."
            />
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              {kits.data.map((k) => (
                <KitCard key={k.id} kit={k} />
              ))}
            </div>
          )}
        </div>
        <div className="w-[400px] shrink-0">
          <UploadCard />
        </div>
      </div>
    </AppShell>
  );
}
