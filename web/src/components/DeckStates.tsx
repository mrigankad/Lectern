"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import {
  AlignLeft, BarChart3, Columns2, Columns3, FileStack, Flag, GitBranch, Hash, Heading, LayoutDashboard, LayoutTemplate,
  Lightbulb, ListOrdered, Milestone, Quote, Table2, Users, Workflow, type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { ApiError, errorText } from "@/lib/api";
import type { Deck, LayoutId } from "@/lib/types";
import { ErrorState, LinkButton, LoadingState } from "./ui";

/**
 * The loading, missing and failed-to-load states shared by every deck screen.
 * Returns null when the deck is there and the screen can draw itself.
 */
export function deckProblem(query: UseQueryResult<Deck>, redirecting: boolean): ReactNode | null {
  if (query.isPending) return <LoadingState label="Opening the deck" />;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <ErrorState
        title={missing ? "This deck does not exist" : "The deck could not be opened"}
        message={missing ? "It may have been deleted, or the link is wrong." : errorText(query.error)}
        onRetry={missing ? undefined : () => query.refetch()}
      >
        <LinkButton href="/" size="sm">
          Back to all decks
        </LinkButton>
      </ErrorState>
    );
  }
  if (redirecting) return <LoadingState label="Taking you to the right step" />;
  return null;
}

const ICONS: Partial<Record<LayoutId, LucideIcon>> = {
  title: Heading,
  agenda: ListOrdered,
  section: Flag,
  big_idea: Lightbulb,
  bullets: AlignLeft,
  two_column: Columns2,
  three_column: Columns3,
  process: Workflow,
  timeline: Milestone,
  chart: BarChart3,
  dashboard: LayoutDashboard,
  table: Table2,
  quote: Quote,
  diagram: GitBranch,
  team: Users,
  appendix: FileStack,
  big_number: Hash,
};

export function LayoutIcon({ layout, size = 16 }: { layout: string; size?: number }) {
  const Icon = ICONS[layout as LayoutId] ?? LayoutTemplate;
  return <Icon size={size} aria-hidden />;
}
