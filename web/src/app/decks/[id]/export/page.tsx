"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, FileText, Image as ImageIcon, Link2, MessageSquareText, MonitorPlay, Presentation, RotateCw, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { deckProblem } from "@/components/DeckStates";
import { AppShell, StepChip } from "@/components/Shell";
import { SlideCanvas } from "@/components/SlideCanvas";
import { ProviderLogo } from "@/components/ProviderLogo";
import { Button, buttonClass, Card, ErrorState, LinkButton, LoadingState, PageHeader, Pill, Toggle } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import type { ExportFormat } from "@/lib/types";
import { fileSize, plural } from "@/lib/format";
import { useDeck, useDeckGate, useRender } from "@/lib/hooks";

const FORMATS: { id: ExportFormat; icon: LucideIcon; name: string; hint: string; check: string; download: string; building: string }[] = [
  { id: "pptx", icon: Presentation, name: "Editable PowerPoint", hint: ".pptx · every object stays editable", check: "Editability check · PowerPoint", download: "Download .pptx", building: "Building the PowerPoint file and checking every object" },
  { id: "pdf", icon: FileText, name: "PDF", hint: "For reading and printing", check: "PDF · vector, fonts embedded", download: "Download .pdf", building: "Drawing the PDF" },
  { id: "images", icon: ImageIcon, name: "Images", hint: "One PNG per slide", check: "Images · one PNG per slide", download: "Download .zip", building: "Drawing one image per slide" },
  { id: "notes", icon: MessageSquareText, name: "Speaker notes", hint: "A script you can print", check: "Speaker notes · Markdown", download: "Download notes", building: "Collecting the speaker notes" },
];

const LATER: { icon: LucideIcon; logo?: string; name: string; hint: string }[] = [
  { icon: MonitorPlay, logo: "google_slides", name: "Google Slides", hint: "Saved to your Google Drive" },
  { icon: Link2, name: "Web link", hint: "A page anyone can open" },
];

export default function ExportPage() {
  const { id } = useParams<{ id: string }>();
  const query = useDeck(id);
  const deck = query.data;
  const redirecting = useDeckGate(deck, "export");
  const usable = Boolean(deck) && !redirecting && deck?.status === "ready";
  const [includeNotes, setIncludeNotes] = useState(true);
  const [format, setFormat] = useState<ExportFormat>("pptx");
  const current = FORMATS.find((f) => f.id === format) ?? FORMATS[0];
  const render = useRender(id, usable);

  // Building the file is what produces the editability report, so it runs as soon as the page opens
  // and again when an option changes. Keyed on the deck's last edit so a changed deck is rebuilt.
  const built = useQuery({
    queryKey: ["export", id, format, includeNotes, deck?.updated_at, deck?.theme?.brand_kit_id],
    queryFn: () => api.exportDeck(id, includeNotes, format),
    enabled: usable,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });

  const problem = deckProblem(query, redirecting);
  const result = built.data;
  const report = result?.report;
  const pct = report && report.total_objects > 0 ? Math.floor((report.editable_objects / report.total_objects) * 100) : 100;
  const preview = (render.data ?? []).slice(0, 3);
  const more = Math.max(0, (deck?.slides.length ?? 0) - preview.length);
  const isPptx = result?.filename.toLowerCase().endsWith(".pptx");

  return (
    <AppShell
      crumbs={[{ label: "Home", href: "/" }, { label: deck?.title || "Deck", href: `/decks/${id}` }, { label: "Export" }]}
      chip={<StepChip step={7} />}
      actions={
        <LinkButton href={`/decks/${id}`} size="sm">
          <ArrowLeft size={15} /> Back to deck
        </LinkButton>
      }
    >
      {problem ?? (
        <>
          <PageHeader icon={<Download size={22} />} title="Export" subtitle="Your deck stays in Lectern either way." />
          <div className="flex items-start gap-4">
            <Card className="w-[280px] shrink-0 overflow-hidden">
              <div className="label px-4 pb-2 pt-3.5">Format</div>
              <div role="radiogroup" aria-label="Format">
                {FORMATS.map(({ id: fid, icon: Icon, name, hint }) => {
                  const on = fid === format;
                  return (
                    <button
                      key={fid}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => setFormat(fid)}
                      className={`flex w-full items-center gap-3 border-t border-line px-4 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-action ${on ? "bg-action-soft" : "hover:bg-surface"}`}
                    >
                      <Icon size={20} className={`shrink-0 ${on ? "text-action" : "text-ink"}`} aria-hidden />
                      <div className="flex min-w-0 grow flex-col">
                        <span className="text-[14px] font-bold leading-[18px] text-ink">{name}</span>
                        <span className="text-[12px] leading-4 text-body">{hint}</span>
                      </div>
                      {on ? (
                        <Check size={18} className="shrink-0 text-action" aria-label="Selected" />
                      ) : (
                        <span className="size-[18px] shrink-0 rounded-pill border border-line-strong" aria-hidden />
                      )}
                    </button>
                  );
                })}
              </div>
              <div className="label border-t border-line px-4 pb-2 pt-3.5">Coming later</div>
              <ul aria-label="Formats that are not available yet">
                {LATER.map(({ icon: Icon, logo, name, hint }) => (
                  <li key={name} className="flex cursor-default items-center gap-3 border-t border-line px-4 py-2.5 text-muted">
                    {logo ? <ProviderLogo id={logo} label={name} size={22} /> : <Icon size={20} className="shrink-0" aria-hidden />}
                    <div className="flex min-w-0 grow flex-col">
                      <span className="text-[14px] leading-[18px]">{name}</span>
                      <span className="text-[12px] leading-4">{hint}</span>
                    </div>
                    <span className="shrink-0 text-[11px] leading-[14px]">Not yet</span>
                  </li>
                ))}
              </ul>
            </Card>

            <div className="flex min-w-0 grow basis-0 flex-col gap-4">
              <Card className="flex flex-col gap-5 p-5">
                {built.isPending ? (
                  <LoadingState label={current.building} className="py-14" />
                ) : built.isError ? (
                  <ErrorState title="The file could not be built" message={errorText(built.error)} onRetry={() => built.refetch()} />
                ) : report && result ? (
                  <>
                    <div className="flex flex-col gap-1">
                      <span className="label">{current.check}</span>
                      {format !== "pptx" ? (
                        <div className="flex flex-wrap items-end gap-x-5 gap-y-1">
                          <span className="text-[96px] font-bold leading-[84px] tracking-[-0.04em] text-ink">
                            {format === "notes" ? report.notes_slides : deck?.slides.length ?? 0}
                          </span>
                          <span className="pb-1 text-[20px] font-bold leading-6 text-ink">
                            {format === "pdf" ? "pages, drawn as vectors" : format === "images" ? "PNG images, 1920 × 1080" : `of ${plural(deck?.slides.length ?? 0, "slide")} have notes`}
                          </span>
                        </div>
                      ) : null}
                      <div className={`flex flex-wrap items-end gap-x-5 gap-y-1 ${format !== "pptx" ? "hidden" : ""}`}>
                        <span className="text-[96px] font-bold leading-[84px] tracking-[-0.04em] text-ink">{pct}%</span>
                        <div className="flex flex-col gap-0.5 pb-1">
                          <span className="text-[20px] font-bold leading-6 text-ink">
                            {report.editable_objects} of {plural(report.total_objects, "object")} stay editable
                          </span>
                          <span className="text-[14px] leading-5 text-body">
                            {report.pictures === 0
                              ? "Nothing is flattened into a picture. Open it and change anything."
                              : `${plural(report.pictures, "picture")} cannot be edited as objects. Everything else can.`}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className={`flex flex-wrap gap-2 ${format === "notes" ? "hidden" : ""}`}>
                      <Pill>{plural(report.text_boxes, "text box", "text boxes")}</Pill>
                      <Pill>{plural(report.charts, "chart")}</Pill>
                      <Pill>{plural(report.tables, "table")}</Pill>
                      <Pill>{plural(report.pictures, "picture")}</Pill>
                      <Pill>{plural(report.notes_slides, "slide")} with notes</Pill>
                    </div>

                    <ul className="rounded-control border border-line">
                      {report.checks.length === 0 ? <li className="px-3.5 py-3 text-[13px] text-body">The server returned no individual checks.</li> : null}
                      {report.checks.map((c, i) => (
                        <li key={`${c.label}-${i}`} className={`flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3.5 py-2.5 ${i ? "border-t border-line" : ""}`}>
                          {c.ok ? <Check size={18} strokeWidth={2.5} className="shrink-0 text-pass" aria-label="Passed" /> : <AlertTriangle size={18} className="shrink-0 text-warn" aria-label="Needs attention" />}
                          <span className="min-w-[180px] grow basis-0 text-[14px] font-bold leading-5 text-ink">{c.label}</span>
                          <span className="text-[13px] leading-5 text-body">{c.detail}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}

                {format === "pptx" || format === "pdf" ? (
                  <div className="flex flex-wrap items-center gap-5">
                    <Toggle checked={includeNotes} onChange={setIncludeNotes} label={format === "pdf" ? "Add a notes page after each slide" : "Include speaker notes"} disabled={built.isFetching} />
                    {deck?.theme?.brand_kit_id && format === "pptx" ? (
                      <span className="text-[13px] leading-5 text-body">Built on your brand kit&apos;s template and layouts.</span>
                    ) : null}
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center gap-4 border-t border-line pt-4">
                  {result ? (
                    <a href={api.fileUrl(result.file_id)} download={result.filename} className={buttonClass("primary", "lg")}>
                      <Download size={18} /> {isPptx || format !== "pptx" ? current.download : "Download file"}
                    </a>
                  ) : (
                    <Button variant="primary" size="lg" disabled>
                      <Download size={18} /> {current.download}
                    </Button>
                  )}
                  {result ? (
                    <div className="flex min-w-0 items-center gap-2.5">
                      <CheckCircle2 size={20} className="shrink-0 text-pass" aria-hidden />
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate text-[14px] font-bold leading-[18px] text-ink">
                          Ready: {result.filename} · {fileSize(result.bytes)}
                        </span>
                        <span className="text-[13px] leading-[18px] text-body">Built from the deck as it is right now</span>
                      </div>
                    </div>
                  ) : null}
                  {result ? (
                    <Button size="sm" variant="ghost" className="ml-auto" busy={built.isFetching} onClick={() => built.refetch()}>
                      {built.isFetching ? null : <RotateCw size={15} />} Build again
                    </Button>
                  ) : null}
                </div>
              </Card>
            </div>

            <Card className="flex w-[300px] shrink-0 flex-col gap-3 bg-surface p-4">
              <div className="flex flex-col gap-0.5">
                <span className="label">Preview</span>
                <span className="text-[13px] leading-[19px] text-body">How the first slides will look when you open the file.</span>
              </div>
              {render.isPending ? (
                <LoadingState label="Drawing slides" className="py-8" />
              ) : render.isError ? (
                <p className="text-[13px] text-fail">The preview could not be drawn. {errorText(render.error)}</p>
              ) : (
                preview.map((r) => (
                  <div key={r.id} className="flex gap-2.5">
                    <span className="w-3.5 shrink-0 text-[12px] font-bold leading-4 text-muted">{r.index}</span>
                    <div className="min-w-0 grow overflow-hidden rounded-chip border border-line-strong">
                      <SlideCanvas slide={r} />
                    </div>
                  </div>
                ))
              )}
              {more > 0 && !render.isPending ? <span className="pl-6 text-[13px] text-body">and {plural(more, "more slide")}</span> : null}
            </Card>
          </div>
        </>
      )}
    </AppShell>
  );
}
