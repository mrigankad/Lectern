"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Database, Download, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/Shell";
import { AttachTools, SourceIcon, sourceMeta } from "@/components/sources/SourceParts";
import { Button, Card, EmptyState, ErrorState, InlineError, LoadingState, PageHeader, Pill } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { useDecks } from "@/lib/hooks";
import type { DataSource } from "@/lib/types";

function Preview({ source }: { source: DataSource }) {
  const [sheet, setSheet] = useState<string | undefined>(undefined);
  const q = useQuery({ queryKey: keys.sourcePreview(source.id, sheet), queryFn: () => api.previewSource(source.id, sheet) });
  if (q.isLoading) return <LoadingState label="Reading" className="py-6" />;
  if (q.isError) return <InlineError>{errorText(q.error)}</InlineError>;
  const data = q.data!;
  return (
    <div className="flex flex-col gap-2">
      {data.sheets.length > 1 ? (
        <div className="flex flex-wrap gap-1">
          {data.sheets.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSheet(s)}
              aria-pressed={s === data.sheet}
              className={s === data.sheet ? "rounded-chip bg-action-soft px-2 py-1 text-[12px] font-bold text-action" : "rounded-chip px-2 py-1 text-[12px] text-body hover:bg-surface"}
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}
      {data.rows ? (
        <div className="max-h-[280px] overflow-auto rounded-control border border-line">
          <table className="w-full border-collapse text-[12px] leading-4">
            <tbody>
              {data.rows.slice(0, 40).map((row, r) => (
                <tr key={r} className="border-b border-line last:border-0">
                  <th scope="row" className="w-8 bg-surface px-1.5 text-right font-normal text-muted">{r + 1}</th>
                  {row.map((c, i) => (
                    <td key={i} className={r === 0 ? "truncate px-2 py-1 font-bold text-ink" : "truncate px-2 py-1 text-ink"}>{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data.chunks.slice(0, 4).map((c) => (
        <p key={c.ref + c.text.slice(0, 12)} className="rounded-control bg-surface p-2.5 text-[13px] leading-5 text-body">
          <span className="font-bold text-ink">{c.ref}</span> {c.text.slice(0, 320)}
          {c.text.length > 320 ? "…" : ""}
        </p>
      ))}
    </div>
  );
}

function Row({ source, deckTitle }: { source: DataSource; deckTitle?: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const reload = useMutation({
    mutationFn: () => api.reloadSource(source.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources"] });
      qc.invalidateQueries({ queryKey: ["source-preview", source.id] });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteSource(source.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });
  return (
    <li className="flex flex-col gap-3 border-b border-line px-4 py-3 last:border-0">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex min-w-0 grow basis-0 items-center gap-2.5 text-left">
          {open ? <ChevronDown size={16} className="shrink-0 text-body" /> : <ChevronRight size={16} className="shrink-0 text-body" />}
          <SourceIcon kind={source.kind} size={18} />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-[14px] font-bold leading-5 text-ink">{source.name}</span>
            <span className="truncate text-[12px] leading-4 text-muted">
              {sourceMeta(source)} · read {new Date(source.updated_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
            </span>
          </span>
        </button>
        {source.deck_id ? (
          <Link href={`/decks/${source.deck_id}/data`} className="max-w-[220px] truncate">
            <Pill tone="action">{deckTitle ?? "Deck"}</Pill>
          </Link>
        ) : (
          <Pill>Not in a deck</Pill>
        )}
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="ghost" onClick={() => reload.mutate()} busy={reload.isPending} title={source.url ? "Fetch the link again" : "Read the file again"}>
            <RefreshCw size={14} /> Refresh
          </Button>
          {source.kind !== "url" && source.kind !== "gsheet" ? (
            <a href={api.sourceFileUrl(source.id)} className="inline-flex h-[30px] items-center gap-1.5 rounded-control px-3 text-[13px] font-bold text-ink hover:bg-surface">
              <Download size={14} /> Download
            </a>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => remove.mutate()} busy={remove.isPending} aria-label={`Delete ${source.name}`}>
            <Trash2 size={14} />
          </Button>
        </div>
      </div>
      <InlineError>{reload.isError ? errorText(reload.error) : remove.isError ? errorText(remove.error) : null}</InlineError>
      {open ? <Preview source={source} /> : null}
    </li>
  );
}

export default function SourcesPage() {
  const qc = useQueryClient();
  const sources = useQuery({ queryKey: keys.sources(), queryFn: () => api.listSources() });
  const decks = useDecks();
  const titles = new Map((decks.data ?? []).map((d) => [d.id, d.title]));
  return (
    <AppShell crumbs={[{ label: "Home", href: "/" }, { label: "Data sources" }]}>
      <PageHeader
        icon={<Database size={22} />}
        title="Data sources"
        subtitle="Spreadsheets, documents and links Lectern reads. Charts made from a sheet stay linked to its cells."
      />
      <Card className="flex flex-col gap-2 p-4">
        <span className="text-[14px] font-bold text-ink">Add a source</span>
        <p className="text-[13px] leading-5 text-body">
          Excel (.xlsx), CSV, PDF, Word (.docx), text and Markdown files, a web page link, or a public Google Sheets
          link. Google sign-in is not available yet, so a sheet must be shared as “Anyone with the link”.
        </p>
        <AttachTools onAdded={() => qc.invalidateQueries({ queryKey: ["sources"] })} />
      </Card>
      {sources.isLoading ? <LoadingState label="Loading data sources" /> : null}
      {sources.isError ? <ErrorState message={errorText(sources.error)} onRetry={() => sources.refetch()} /> : null}
      {sources.data && sources.data.length === 0 ? (
        <EmptyState icon={<Database size={22} />} title="No data sources yet" message="Attach a file above, or on the new-deck screen, and it shows up here." />
      ) : null}
      {sources.data && sources.data.length > 0 ? (
        <Card>
          <ul>
            {sources.data.map((s) => (
              <Row key={s.id} source={s} deckTitle={s.deck_id ? titles.get(s.deck_id) : undefined} />
            ))}
          </ul>
        </Card>
      ) : null}
    </AppShell>
  );
}
