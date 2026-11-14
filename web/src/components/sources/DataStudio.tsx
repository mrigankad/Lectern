"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, AreaChart, BarChart3, Check, LineChart, Link2, PencilLine, PieChart, Plus, RefreshCw, Table2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChartSvg } from "@/components/ChartSvg";
import { deckProblem } from "@/components/DeckStates";
import { AppShell } from "@/components/Shell";
import { Button, Card, Dropdown, EmptyState, ErrorState, InlineError, LoadingState, Pill, Segmented } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { cx } from "@/lib/format";
import { useDeck } from "@/lib/hooks";
import type { ChartKind, ChartSuggestion, DataSource } from "@/lib/types";
import { AttachTools, SourceIcon } from "./SourceParts";

type Sel = { r0: number; c0: number; r1: number; c1: number };
type ShowAs = ChartKind | "table";

function colName(i: number): string {
  let n = i + 1;
  let s = "";
  while (n) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}
const a1 = (s: Sel) => `${colName(s.c0)}${s.r0 + 1}:${colName(s.c1)}${s.r1 + 1}`;
const norm = (a: { r: number; c: number }, b: { r: number; c: number }): Sel => ({
  r0: Math.min(a.r, b.r), c0: Math.min(a.c, b.c), r1: Math.max(a.r, b.r), c1: Math.max(a.c, b.c),
});
const NUMERIC = /^\s*[-+(]?[$€£₹]?\s*[-+]?[\d,]*\.?\d+\s*([kKmMbB]|bn)?\s*(%|pts?|pp|x)?\)?\s*$/;

/** The first block of filled rows, label column plus the next column: a sensible starting selection. */
function defaultSel(rows: string[][]): Sel | null {
  const start = rows.findIndex((r) => r.some((c) => c.trim()));
  if (start < 0) return null;
  let end = start;
  while (end + 1 < rows.length && rows[end + 1].some((c) => c.trim())) end++;
  while (end > start + 2 && /^(total|sum|change|avg|average|delta|diff)/i.test(rows[end][0] ?? "")) end--;
  const width = Math.max(...rows.slice(start, end + 1).map((r) => r.length));
  return { r0: start, c0: 0, r1: end, c1: Math.min(1, width - 1) };
}

function parseRef(ref: string): { source: string; sheet: string; sel: Sel } | null {
  const m = ref.match(/^(.*)!(.*)!\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$/i);
  if (!m) return null;
  const col = (s: string) => s.toUpperCase().split("").reduce((v, ch) => v * 26 + ch.charCodeAt(0) - 64, 0) - 1;
  const sel = norm({ r: Number(m[4]) - 1, c: col(m[3]) }, { r: Number(m[6] ?? m[4]) - 1, c: col(m[5] ?? m[3]) });
  return { source: m[1], sheet: m[2].replace(/^'(.*)'$/, "$1"), sel };
}

const KIND_ICON: Record<ShowAs, typeof BarChart3> = { bar: BarChart3, line: LineChart, area: AreaChart, pie: PieChart, table: Table2 };
const KIND_LABEL: Record<ShowAs, string> = { bar: "Bar", line: "Line", area: "Area", pie: "Pie", table: "Table" };

function Steps({ step }: { step: 1 | 2 | 3 }) {
  const labels = ["Pick the cells", "Check the chart", "Insert it"];
  return (
    <ol className="hidden items-center gap-4 lg:flex" aria-label="Steps">
      {labels.map((l, i) => {
        const n = i + 1;
        const state = n < step ? "done" : n === step ? "now" : "next";
        return (
          <li key={l} className="flex items-center gap-2 text-[14px] leading-5" aria-current={state === "now" ? "step" : undefined}>
            <span
              className={cx(
                "flex size-5 items-center justify-center rounded-pill text-[11px] font-bold",
                state === "now" ? "bg-action text-white" : state === "done" ? "bg-pass-soft text-pass" : "bg-surface-2 text-body",
              )}
            >
              {n}
            </span>
            <span className={state === "now" ? "font-bold text-ink" : "text-body"}>{l}</span>
          </li>
        );
      })}
    </ol>
  );
}

function SheetGrid({ rows, sel, onSelect }: { rows: string[][]; sel: Sel | null; onSelect: (s: Sel) => void }) {
  const anchor = useRef<{ r: number; c: number } | null>(null);
  const [drag, setDragState] = useState<Sel | null>(null);
  // The live range also lives in a ref, so a fast drag (move and release in one frame) still commits it.
  const dragRef = useRef<Sel | null>(null);
  const setDrag = (s: Sel | null) => {
    dragRef.current = s;
    setDragState(s);
  };
  const width = Math.max(1, ...rows.map((r) => r.length));
  const shown = drag ?? sel;
  const inSel = (r: number, c: number) => !!shown && r >= shown.r0 && r <= shown.r1 && c >= shown.c0 && c <= shown.c1;
  const visibleRows = Math.max(rows.length + 1, 10);

  useEffect(() => {
    const up = (e: MouseEvent) => {
      const start = anchor.current;
      if (start) {
        // Use the cell under the pointer at release, in case no mouseenter fired on the way.
        const cell = (e.target as HTMLElement | null)?.closest?.("td[data-r]") as HTMLElement | null;
        const end = cell ? { r: Number(cell.dataset.r), c: Number(cell.dataset.c) } : null;
        const range = end ? norm(start, end) : dragRef.current;
        if (range) onSelect(range);
      }
      anchor.current = null;
      dragRef.current = null;
      setDragState(null);
    };
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, [onSelect]);

  const lastRow = Math.max(0, rows.length - 1);
  return (
    <div className="max-h-[420px] overflow-auto rounded-control border border-line select-none" role="grid" aria-label="Sheet cells. Drag to pick a range.">
      <table className="w-full border-collapse text-[13px] leading-4">
        <thead className="sticky top-0 z-10">
          <tr>
            <th className="w-8 border-b border-r border-line bg-surface" />
            {Array.from({ length: width }, (_, c) => (
              <th
                key={c}
                scope="col"
                onClick={() => onSelect({ r0: 0, c0: c, r1: lastRow, c1: c })}
                className={cx(
                  "h-7 min-w-[64px] cursor-pointer border-b border-r border-line text-[11px] font-bold",
                  shown && c >= shown.c0 && c <= shown.c1 ? "bg-action text-white" : "bg-surface text-body",
                )}
              >
                {colName(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: visibleRows }, (_, r) => (
            <tr key={r}>
              <th scope="row" className="h-[29px] w-8 border-b border-r border-line bg-surface text-[11px] font-normal text-muted">
                {r + 1}
              </th>
              {Array.from({ length: width }, (_, c) => {
                const text = rows[r]?.[c] ?? "";
                const on = inSel(r, c);
                const header = r === 0 && text && !NUMERIC.test(text);
                return (
                  <td
                    key={c}
                    role="gridcell"
                    aria-selected={on}
                    data-r={r}
                    data-c={c}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      if (e.shiftKey && sel) {
                        onSelect(norm({ r: sel.r0, c: sel.c0 }, { r, c }));
                        return;
                      }
                      anchor.current = { r, c };
                      setDrag(norm({ r, c }, { r, c }));
                    }}
                    onMouseEnter={() => {
                      if (anchor.current) setDrag(norm(anchor.current, { r, c }));
                    }}
                    className={cx(
                      "h-[29px] max-w-[160px] cursor-cell truncate border-b border-r border-line px-2",
                      NUMERIC.test(text) ? "text-right" : "text-left",
                      header ? "font-bold text-ink" : "text-ink",
                      on && "bg-action-soft",
                    )}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcePane({
  sources, source, setSourceId, sheet, setSheet, sel, setSel, deckId,
}: {
  sources: DataSource[]; source: DataSource | undefined; setSourceId: (id: string) => void; sheet: string | undefined;
  setSheet: (s: string) => void; sel: Sel | null; setSel: (s: Sel) => void; deckId: string;
}) {
  const qc = useQueryClient();
  const preview = useQuery({
    queryKey: keys.sourcePreview(source?.id ?? "", sheet),
    queryFn: () => api.previewSource(source!.id, sheet),
    enabled: !!source,
  });
  const rows = preview.data?.rows;
  useEffect(() => {
    if (rows && !sel) {
      const d = defaultSel(rows);
      if (d) setSel(d);
    }
  }, [rows, sel, setSel]);

  return (
    <Card className="flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        {source ? <SourceIcon kind={source.kind} size={18} /> : null}
        {sources.length > 1 ? (
          <Dropdown
            value={source?.id ?? ""}
            onChange={setSourceId}
            ariaLabel="Data source"
            options={sources.map((s) => ({ value: s.id, label: s.name }))}
            triggerClassName="h-8 border-0 px-1 text-[17px] font-bold"
          />
        ) : (
          <span className="truncate text-[17px] font-bold leading-6 text-ink">{source?.name}</span>
        )}
        <span className="ml-auto shrink-0 text-[12px] leading-4 text-muted">
          {source ? `Read ${new Date(source.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}
        </span>
      </div>
      {preview.isLoading ? <LoadingState label="Reading the sheet" className="py-10" /> : null}
      {preview.isError ? <InlineError>{errorText(preview.error)}</InlineError> : null}
      {preview.data && !rows ? (
        <p className="rounded-control bg-surface p-3 text-[13px] leading-5 text-body">
          This source is text, not a sheet. The Analyst reads its numbers and cites the page or paragraph; pick a
          spreadsheet or CSV to make a chart.
        </p>
      ) : null}
      {rows ? <SheetGrid rows={rows} sel={sel} onSelect={setSel} /> : null}
      {preview.data && preview.data.sheets.length > 1 ? (
        <div role="tablist" aria-label="Sheets" className="flex gap-1 overflow-x-auto border-b border-line">
          {preview.data.sheets.map((s) => (
            <button
              key={s}
              role="tab"
              type="button"
              aria-selected={s === preview.data?.sheet}
              onClick={() => setSheet(s)}
              className={cx(
                "-mb-px shrink-0 border-b-2 px-3 py-2 text-[13px] leading-4",
                s === preview.data?.sheet ? "border-action font-bold text-ink" : "border-transparent text-body hover:text-ink",
              )}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
      {sel && rows ? (
        <div className="rounded-control bg-surface p-3">
          <div className="text-[12px] leading-4 text-muted">Selected cells</div>
          <div className="text-[14px] font-bold leading-5 text-ink">
            {preview.data?.sheet} sheet, {colName(sel.c0)}{sel.r0 + 1} to {colName(sel.c1)}{sel.r1 + 1}
          </div>
          <div className="text-[13px] leading-5 text-body">Drag on the sheet to pick different cells. Click a column letter to take the whole column.</div>
        </div>
      ) : null}
      <AttachTools
        deckId={deckId}
        onAdded={(s) => {
          qc.invalidateQueries({ queryKey: ["sources"] });
          setSourceId(s.id);
        }}
      />
    </Card>
  );
}

function Studio({ deckId, slideId }: { deckId: string; slideId: string | null }) {
  const qc = useQueryClient();
  const router = useRouter();
  const deck = useDeck(deckId);
  const sources = useQuery({ queryKey: keys.sources(deckId), queryFn: () => api.listSources(deckId) });
  const slides = deck.data?.slides ?? [];
  const slide = slides.find((s) => s.id === slideId) ?? slides.find((s) => s.layout === "chart") ?? slides[0];
  const slideData = useQuery({
    queryKey: keys.slideData(deckId, slide?.id ?? ""),
    queryFn: () => api.getSlideData(deckId, slide!.id),
    enabled: !!slide,
  });
  const linkedRef = slideData.data?.linked.find((l) => l.type === "chart")?.data_ref ?? slideData.data?.linked[0]?.data_ref;
  const linked = linkedRef ? parseRef(linkedRef) : null;
  // The chart node already on the slide (kind, title, unit), so a reload shows what the slide has.
  const linkedChart = slide?.nodes.find(
    (nd): nd is Extract<typeof nd, { type: "chart" }> => nd.type === "chart" && (!linkedRef || nd.data_ref === linkedRef),
  ) ?? slide?.nodes.find((nd): nd is Extract<typeof nd, { type: "chart" }> => nd.type === "chart");

  const [sourceId, setSourceId] = useState<string | null>(null);
  const [sheet, setSheet] = useState<string | undefined>(undefined);
  const [sel, setSel] = useState<Sel | null>(null);
  const [showAs, setShowAs] = useState<ShowAs | null>(null);
  const [insertAs, setInsertAs] = useState<"chart" | "stat">("chart");
  const [useHeadline, setUseHeadline] = useState(true);
  const seeded = useRef(false);
  // Selection key the seeded chart kind belongs to; the reset below leaves it alone for that selection.
  const seededKey = useRef<string | null>(null);

  // Start from what the slide already links to, else the newest sheet.
  useEffect(() => {
    if (seeded.current || !sources.data || !slideData.data) return;
    seeded.current = true;
    const own = linked ? sources.data.find((s) => s.name === linked.source) : undefined;
    if (own && linked) {
      setSourceId(own.id);
      setSheet(linked.sheet);
      setSel(linked.sel);
      if (linkedChart) {
        setShowAs(linkedChart.kind);
        setInsertAs("chart");
        seededKey.current = `${own.id}|${linked.sheet ?? ""}|${a1(linked.sel)}`;
      }
      return;
    }
    const sheetLike = sources.data.find((s) => s.summary.sheets.length > 0) ?? sources.data[0];
    if (sheetLike) setSourceId(sheetLike.id);
  }, [sources.data, slideData.data, linked, linkedChart]);

  const source = sources.data?.find((s) => s.id === sourceId);
  const range = sel ? a1(sel) : "";
  const suggestion = useQuery({
    queryKey: ["chart-suggest", sourceId, sheet ?? "", range],
    queryFn: () => api.suggestChart(sourceId!, sheet, range),
    enabled: !!sourceId && !!range && (source?.summary.sheets.length ?? 0) > 0,
  });
  useEffect(() => {
    if (seededKey.current && seededKey.current === `${sourceId}|${sheet ?? ""}|${range}`) return;
    seededKey.current = null;
    setShowAs(null);
  }, [range, sourceId, sheet]);
  const s: ChartSuggestion | undefined = suggestion.data;
  const kind: ShowAs = showAs ?? s?.kind ?? "bar";

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: keys.deck(deckId) });
    qc.invalidateQueries({ queryKey: keys.render(deckId) });
    qc.invalidateQueries({ queryKey: keys.critic(deckId) });
    if (slide) qc.invalidateQueries({ queryKey: keys.slideData(deckId, slide.id) });
  };
  const insert = useMutation({
    mutationFn: () =>
      api.insertData(deckId, slide!.id, {
        data_ref: s!.data_ref,
        as: insertAs,
        kind: insertAs === "chart" ? kind : undefined,
        title: insertAs === "chart" ? linkedChart?.title : undefined,
        headline: insertAs === "chart" && useHeadline && s?.headline ? s.headline : undefined,
      }),
    onSuccess: invalidate,
  });
  const refresh = useMutation({ mutationFn: () => api.refreshData(deckId, slide!.id), onSuccess: invalidate });
  const fix = useMutation({ mutationFn: () => api.fixDataNumbers(deckId, slide!.id), onSuccess: invalidate });

  const themeColors = deck.data?.theme.chart_colors;
  const colors = useMemo(() => themeColors ?? ["#2563EB"], [themeColors]);
  const chart = useMemo(
    () =>
      s?.ok && kind !== "table"
        ? { kind: kind as ChartKind, categories: s.categories ?? [], series: s.series ?? [], colors, unit: s.unit ?? linkedChart?.unit ?? undefined }
        : null,
    [s, kind, colors, linkedChart?.unit],
  );

  const problem = deckProblem(deck, false);
  if (problem || !deck.data) {
    return <AppShell crumbs={[{ label: "Home", href: "/" }, { label: "Data and charts" }]}>{problem}</AppShell>;
  }
  const n = slide?.index;
  const mismatches = slideData.data?.mismatches ?? [];
  const step: 1 | 2 | 3 = insert.isSuccess ? 3 : s?.ok ? 2 : 1;

  return (
    <AppShell
      crumbs={[
        { label: deck.data.title, href: `/decks/${deckId}` },
        ...(n ? [{ label: `Slide ${n}`, href: `/decks/${deckId}?slide=${slide?.id}` }] : []),
        { label: "Data and charts" },
      ]}
    >
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-pass-soft text-pass">
          <Table2 size={22} />
        </div>
        <div className="flex min-w-0 grow basis-0 flex-col gap-0.5">
          <h1 className="text-[28px] font-bold leading-8 text-ink">Turn your sheet into a chart</h1>
          <p className="text-[15px] leading-5 text-body">
            {n ? `For slide ${n} of ${deck.data.title}` : deck.data.title}
            {source ? `, from ${source.name}.` : "."}
          </p>
        </div>
        <Steps step={step} />
      </div>

      {sources.isLoading ? <LoadingState label="Loading data sources" /> : null}
      {sources.data && sources.data.length === 0 ? (
        <Card className="flex flex-col gap-4 p-6">
          <EmptyState
            title="Add a spreadsheet to this deck"
            message="Attach an Excel or CSV file, or connect a public Google Sheet. Then pick the cells and Lectern suggests the chart."
          />
          <AttachTools
            deckId={deckId}
            className="items-center"
            onAdded={(src) => {
              qc.invalidateQueries({ queryKey: ["sources"] });
              setSourceId(src.id);
            }}
          />
        </Card>
      ) : null}

      {sources.data && sources.data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,330px)_minmax(0,1fr)_minmax(0,300px)]">
          <SourcePane
            sources={sources.data}
            source={source}
            setSourceId={(id) => {
              setSourceId(id);
              setSheet(undefined);
              setSel(null);
            }}
            sheet={sheet}
            setSheet={(name) => {
              setSheet(name);
              setSel(null);
            }}
            sel={sel}
            setSel={setSel}
            deckId={deckId}
          />

          <div className="flex min-w-0 flex-col gap-4">
            <Card className="flex flex-col gap-4 p-5">
              {suggestion.isLoading ? <LoadingState label="Reading the cells" className="py-10" /> : null}
              {suggestion.isError ? <InlineError>{errorText(suggestion.error)}</InlineError> : null}
              {s && !s.ok ? <p className="rounded-control bg-surface p-3 text-[14px] leading-5 text-body">{s.reason}</p> : null}
              {s?.ok ? (
                <>
                  <div className="flex flex-col gap-1.5">
                    <Pill tone="ai" className="self-start">Lectern suggests a {KIND_LABEL[s.kind ?? "bar"].toLowerCase()} chart</Pill>
                    <h2 className="text-[18px] font-bold leading-6 text-ink">{s.headline || s.cells_label}</h2>
                  </div>
                  <div className="w-full [&>svg]:h-auto [&>svg]:w-full" aria-live="polite">
                    {chart ? (
                      <ChartSvg chart={chart} w={1600} h={760} dark={false} surface="#FFFFFF" />
                    ) : (
                      <div className="max-h-[320px] overflow-auto rounded-control border border-line">
                        <table className="w-full text-[13px]">
                          <thead>
                            <tr className="bg-surface">
                              <th className="px-3 py-2 text-left">{""}</th>
                              {s.series?.map((x) => <th key={x.name} className="px-3 py-2 text-right font-bold">{x.name}</th>)}
                            </tr>
                          </thead>
                          <tbody>
                            {s.categories?.map((c, i) => (
                              <tr key={c + i} className="border-t border-line">
                                <td className="px-3 py-1.5">{c}</td>
                                {s.series?.map((x) => <td key={x.name} className="px-3 py-1.5 text-right">{x.values[i]}</td>)}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1.5 rounded-control border border-ai-line bg-ai-soft p-4">
                    <div className="flex items-center gap-2 text-[15px] font-bold leading-5 text-ink">
                      Why a {KIND_LABEL[s.kind ?? "bar"].toLowerCase()} chart <Pill tone="ai">AI note</Pill>
                    </div>
                    <p className="text-[14px] leading-[21px] text-ink">{s.reason}</p>
                    {showAs && showAs !== s.kind ? (
                      <p className="text-[13px] leading-5 text-body">
                        You chose {KIND_LABEL[showAs].toLowerCase()}: {s.alternatives?.find((a) => a.kind === showAs)?.reason}
                      </p>
                    ) : null}
                    {s.warnings?.map((w) => <p key={w} className="text-[13px] leading-5 text-warn">{w}</p>)}
                  </div>
                </>
              ) : null}
            </Card>
            {s?.ok ? (
              <Card className="flex flex-col gap-3 p-4">
                <span className="text-[13px] leading-4 text-body">Or show it as</span>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                  {s.alternatives?.map((alt) => {
                    const Icon = KIND_ICON[alt.kind];
                    const on = kind === alt.kind;
                    return (
                      <button
                        key={alt.kind}
                        type="button"
                        aria-pressed={on}
                        disabled={!alt.ok}
                        title={alt.reason}
                        onClick={() => setShowAs(alt.kind)}
                        className={cx(
                          "flex h-10 items-center gap-2 rounded-control border px-3 text-[14px] font-bold",
                          on ? "border-action bg-action-soft text-action" : "border-line-strong text-ink hover:bg-surface",
                          "disabled:cursor-not-allowed disabled:opacity-40",
                        )}
                      >
                        <Icon size={16} aria-hidden /> {KIND_LABEL[alt.kind]}
                        {on ? <Check size={14} className="ml-auto" aria-hidden /> : null}
                      </button>
                    );
                  })}
                </div>
              </Card>
            ) : null}
          </div>

          <div className="flex min-w-0 flex-col gap-4">
            <Card className="flex flex-col">
              <div className="border-b border-line px-4 py-3 text-[17px] font-bold leading-6 text-ink">Chart settings</div>
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
                <span className="text-[14px] text-body">Slide</span>
                <Dropdown
                  value={slide?.id ?? ""}
                  ariaLabel="Slide to insert on"
                  onChange={(id) => router.replace(`/decks/${deckId}/data?slide=${id}`)}
                  options={slides.map((x) => ({ value: x.id, label: `${x.index}. ${x.headline}` }))}
                  minMenuWidth={320}
                  triggerClassName="h-8 max-w-[170px] text-[13px] font-bold"
                />
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
                <span className="text-[14px] text-body">Cells</span>
                <span className="truncate text-[13px] font-bold text-ink">{s?.cells_label ?? "None yet"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
                <span className="text-[14px] text-body">Colours</span>
                <span className="flex items-center gap-1.5 text-[13px] font-bold text-ink">
                  <span className="flex gap-0.5" aria-hidden>
                    {colors.slice(0, 3).map((c) => <span key={c} className="size-2.5 rounded-pill" style={{ background: c }} />)}
                  </span>
                  From the deck theme
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
                <span className="text-[14px] text-body">Insert as</span>
                <Segmented
                  label="Insert as"
                  value={insertAs}
                  onChange={setInsertAs}
                  options={[{ value: "chart", label: "Chart" }, { value: "stat", label: "Big number" }]}
                />
              </div>
              <label className="flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5">
                <span className="text-[14px] text-body">Use the suggested headline</span>
                <input
                  type="checkbox"
                  checked={useHeadline}
                  onChange={(e) => setUseHeadline(e.target.checked)}
                  className="size-4 accent-[var(--action)]"
                  disabled={insertAs !== "chart"}
                />
              </label>
            </Card>

            <Card className="flex flex-col gap-4 p-4">
              <div className="flex gap-3">
                <Link2 size={18} className="mt-0.5 shrink-0 text-ink" aria-hidden />
                <div>
                  <div className="text-[15px] font-bold leading-5 text-ink">Stays linked to the sheet</div>
                  <p className="text-[13px] leading-5 text-body">
                    When {source?.name ?? "the sheet"} changes, refresh and the chart follows. The Critic checks the
                    slide and notes against these cells.
                  </p>
                </div>
              </div>
              <div className="flex gap-3">
                <PencilLine size={18} className="mt-0.5 shrink-0 text-ink" aria-hidden />
                <div>
                  <div className="text-[15px] font-bold leading-5 text-ink">Stays editable in PowerPoint</div>
                  <p className="text-[13px] leading-5 text-body">
                    It goes in as a real chart with its data sheet, not a picture. Anyone can change the numbers or the style.
                  </p>
                </div>
              </div>
            </Card>

            {mismatches.length ? (
              <div className="flex flex-col gap-1.5 rounded-card border border-warn/30 bg-warn-soft p-4" role="status">
                <div className="flex items-center gap-2 text-[15px] font-bold leading-5 text-ink">
                  <AlertTriangle size={18} className="text-warn" aria-hidden />
                  {mismatches.length === 1 ? "1 number does not match the sheet" : `${mismatches.length} numbers do not match the sheet`}
                </div>
                {mismatches.slice(0, 3).map((m) => (
                  <p key={m.key} className="text-[13px] leading-5 text-body">
                    {m.detail}
                  </p>
                ))}
                <div className="flex flex-wrap gap-3 pt-1">
                  {mismatches.some((m) => m.key.startsWith("sheet:")) ? (
                    <button type="button" onClick={() => fix.mutate()} className="text-[14px] font-bold text-warn underline" disabled={fix.isPending}>
                      Update slide {n}
                    </button>
                  ) : null}
                  {mismatches.some((m) => m.key.startsWith("link")) ? (
                    <button type="button" onClick={() => refresh.mutate()} className="text-[14px] font-bold text-warn underline" disabled={refresh.isPending}>
                      Refresh from sheet
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}

            <InlineError>
              {insert.isError ? errorText(insert.error) : refresh.isError ? errorText(refresh.error) : fix.isError ? errorText(fix.error) : null}
            </InlineError>
            {refresh.isSuccess ? (
              <p className="text-[13px] leading-5 text-body" role="status">
                {refresh.data.changed.length ? "The slide now matches the sheet." : "Already up to date with the sheet."}
              </p>
            ) : null}
            {slideData.data?.linked.length ? (
              <Button size="lg" onClick={() => refresh.mutate()} busy={refresh.isPending}>
                <RefreshCw size={18} /> Refresh from sheet
              </Button>
            ) : null}
            <Button variant="primary" size="lg" onClick={() => insert.mutate()} busy={insert.isPending} disabled={!s?.ok || !slide}>
              <Plus size={18} /> Insert on slide {n}
            </Button>
            {insert.isSuccess ? (
              <p className="text-[13px] leading-5 text-body" role="status">
                Inserted on slide {n}.{" "}
                <Link className="font-bold text-action hover:underline" href={`/decks/${deckId}?slide=${slide?.id}`}>
                  See the slide
                </Link>
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
      {sources.isError ? <ErrorState message={errorText(sources.error)} onRetry={() => sources.refetch()} /> : null}
    </AppShell>
  );
}

export { Studio as DataStudio };
