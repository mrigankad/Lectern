"use client";

import Link from "next/link";
import { ChevronRight, Image as ImageIcon } from "lucide-react";
import { AppShell } from "@/components/Shell";
import { Card, EmptyState, ErrorState, LinkButton, LoadingState, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { useDecks } from "@/lib/hooks";

export default function MediaIndexPage() {
  const decks = useDecks();
  const list = [...(decks.data ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return (
    <AppShell crumbs={[{ label: "Library" }, { label: "Media" }]}>
      <PageHeader icon={<ImageIcon size={22} />} title="Media" subtitle="Pictures and videos live with their deck. Pick a deck to make or upload one." />
      {decks.isPending ? (
        <LoadingState label="Loading decks" />
      ) : decks.isError ? (
        <ErrorState title="Decks could not be loaded" message={errorText(decks.error)} onRetry={() => decks.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState icon={<ImageIcon size={20} />} title="No decks yet" message="Make a deck first, then add pictures to its slides.">
          <LinkButton href="/new" variant="primary" size="sm">New deck</LinkButton>
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <ul>
            {list.map((d, i) => (
              <li key={d.id} className={i ? "border-t border-line" : undefined}>
                <Link href={`/decks/${d.id}/media`} className="flex items-center gap-3 px-4 py-3 hover:bg-surface">
                  <span className="min-w-0 grow truncate text-[15px] font-bold text-ink">{d.title || "Untitled deck"}</span>
                  <span className="text-[12px] text-body">{d.slide_count} slides</span>
                  <ChevronRight size={16} className="text-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </AppShell>
  );
}
