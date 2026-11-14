"use client";

import { FileSpreadsheet, FileText, Globe, Link2, Paperclip, X } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { Button, InlineError } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { cx } from "@/lib/format";
import { ProviderLogo } from "@/components/ProviderLogo";
import type { DataSource, SourceKind } from "@/lib/types";

export const ACCEPT = ".xlsx,.xlsm,.csv,.tsv,.pdf,.docx,.txt,.md";

/** File-type icon in its colour: green sheets, red PDF, blue Word, neutral text and links. */
export function SourceIcon({ kind, size = 16 }: { kind: SourceKind; size?: number }) {
  if (kind === "xlsx" || kind === "csv") return <FileSpreadsheet size={size} className="text-pass" aria-hidden />;
  if (kind === "gsheet") return <ProviderLogo id="google_sheets" label="Google Sheets" size={Math.max(20, size + 4)} />;
  if (kind === "pdf") return <FileText size={size} className="text-fail" aria-hidden />;
  if (kind === "docx") return <FileText size={size} className="text-action" aria-hidden />;
  if (kind === "url") return <Globe size={size} className="text-body" aria-hidden />;
  return <FileText size={size} className="text-body" aria-hidden />;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const KIND_LABEL: Record<SourceKind, string> = {
  xlsx: "Excel", csv: "CSV", pdf: "PDF", docx: "Word", text: "Text", url: "Web page", gsheet: "Google Sheet",
};

/** "4 sheets · 212 KB", "6 pages · 88 KB", "Web page". */
export function sourceMeta(s: DataSource): string {
  const parts: string[] = [];
  const sheets = s.summary.sheets.length;
  if (s.kind === "pdf" && s.summary.pages) parts.push(`${s.summary.pages} page${s.summary.pages === 1 ? "" : "s"}`);
  else if (sheets && s.kind !== "docx") parts.push(sheets === 1 ? `${s.summary.sheets[0].rows} rows` : `${sheets} sheets`);
  else if (s.summary.chunks) parts.push(`${s.summary.chunks} passage${s.summary.chunks === 1 ? "" : "s"}`);
  if (s.kind === "url" || s.kind === "gsheet") parts.push(KIND_LABEL[s.kind]);
  else parts.push(formatBytes(s.bytes));
  return parts.join(" · ");
}

export function SourceChip({ source, onRemove }: { source: DataSource; onRemove?: () => void }) {
  return (
    <span className="inline-flex h-8 max-w-full items-center gap-2 rounded-chip border border-line-strong bg-bg pl-2.5 pr-1.5 text-[13px] leading-4">
      <SourceIcon kind={source.kind} />
      <span className="truncate font-bold text-ink" title={source.url ?? source.name}>{source.name}</span>
      <span className="shrink-0 text-muted">{sourceMeta(source)}</span>
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${source.name}`}
          className="flex size-6 shrink-0 items-center justify-center rounded-chip text-body hover:bg-surface-2 hover:text-ink"
        >
          <X size={14} />
        </button>
      ) : null}
    </span>
  );
}

function ToolButton({ icon, children, onClick, pressed }: { icon: ReactNode; children: ReactNode; onClick: () => void; pressed?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={cx(
        "inline-flex h-8 items-center gap-2 rounded-control px-2.5 text-[13px] font-bold leading-4 text-ink hover:bg-surface",
        pressed && "bg-action-soft text-action hover:bg-action-soft",
      )}
    >
      {icon}
      {children}
    </button>
  );
}

/**
 * Attach file / Paste a link / Connect a sheet. Uploads straight away (to the deck when there is one),
 * and hands each new source to `onAdded`.
 */
export function AttachTools({ deckId, onAdded, className }: { deckId?: string; onAdded: (s: DataSource) => void; className?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"link" | "sheet" | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    for (const file of Array.from(files)) {
      try {
        onAdded(await api.uploadSource(file, deckId));
      } catch (e) {
        setError(`${file.name}: ${errorText(e)}`);
      }
    }
    setBusy(false);
    if (input.current) input.current.value = "";
  };

  const addLink = async () => {
    const value = url.trim();
    if (!value) return;
    if (mode === "sheet" && !/docs\.google\.com\/spreadsheets/.test(value)) {
      setError("That is not a Google Sheets link. It should start with https://docs.google.com/spreadsheets/.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onAdded(await api.addSourceLink(value, deckId));
      setUrl("");
      setMode(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cx("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center gap-1">
        <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => void upload(e.target.files)} />
        <ToolButton icon={<Paperclip size={16} />} onClick={() => input.current?.click()}>
          Attach file
        </ToolButton>
        <ToolButton icon={<Link2 size={16} />} pressed={mode === "link"} onClick={() => setMode(mode === "link" ? null : "link")}>
          Paste a link
        </ToolButton>
        <ToolButton icon={<ProviderLogo id="google_sheets" label="Google Sheets" size={20} />} pressed={mode === "sheet"} onClick={() => setMode(mode === "sheet" ? null : "sheet")}>
          Connect a sheet
        </ToolButton>
        {busy ? <span className="pl-1 text-[12px] leading-4 text-muted" role="status">Reading…</span> : null}
      </div>
      {mode ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void addLink();
                }
                if (e.key === "Escape") setMode(null);
              }}
              placeholder={mode === "sheet" ? "https://docs.google.com/spreadsheets/d/…" : "https://…"}
              aria-label={mode === "sheet" ? "Google Sheets link" : "Link to a web page"}
              className="h-9 min-w-0 grow rounded-control border border-line-strong bg-bg px-3 text-[14px] text-ink placeholder:text-muted focus:border-action"
            />
            <Button size="md" variant="primary" onClick={() => void addLink()} busy={busy} disabled={!url.trim()}>
              {mode === "sheet" ? "Connect" : "Add link"}
            </Button>
          </div>
          <p className="text-[12px] leading-4 text-body">
            {mode === "sheet"
              ? "Google Sheets connect through a public link for now: in Sheets choose Share, set “Anyone with the link” can view, then paste it here. Signing in with Google is not available yet."
              : "Lectern reads the text of the page and cites it."}
          </p>
        </div>
      ) : null}
      <InlineError>{error}</InlineError>
    </div>
  );
}
