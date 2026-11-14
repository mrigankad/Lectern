"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api, keys } from "./api";
import type { Deck, DeckStatus } from "./types";

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.health,
    // While the API is down, check again sooner with backoff (2s, 4s, 8s, then every 15s) so it recovers.
    refetchInterval: (q) => (q.state.status === "error" ? errorBackoff(q.state.errorUpdateCount) : 15_000),
    retry: false,
    staleTime: 0,
  });
}

export function useDecks() {
  return useQuery({
    queryKey: keys.decks,
    queryFn: api.listDecks,
    // The list has no event stream of its own, so poll gently while something is in motion.
    refetchInterval: (q) =>
      q.state.status === "error"
        ? errorBackoff(q.state.errorUpdateCount)
        : q.state.data?.some((d) => d.status === "building" || d.status === "draft") ? 4_000 : false,
  });
}

/** Delay before the next try after `failures` failed loads: 2s, 4s, 8s, capped at 15s. */
function errorBackoff(failures: number): number {
  return Math.min(15_000, 1_000 * 2 ** Math.max(1, failures));
}

export function useDeck(id: string) {
  return useQuery({
    queryKey: keys.deck(id),
    queryFn: () => api.getDeck(id),
    // Events drive updates; this slow poll is only a safety net if the stream drops.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "draft" ? 2_500 : s === "building" ? 5_000 : false;
    },
  });
}

export function useRender(id: string, enabled = true) {
  return useQuery({ queryKey: keys.render(id), queryFn: () => api.getRender(id), enabled });
}

export type DeckScreen = "interview" | "outline" | "build" | "workspace" | "review" | "export";

/** Where a deck belongs for its status. */
export function screenFor(status: DeckStatus): DeckScreen {
  if (status === "interview") return "interview";
  if (status === "draft" || status === "outline_ready") return "outline";
  if (status === "building" || status === "failed") return "build";
  return "workspace";
}

export function deckHref(id: string, status: DeckStatus): string {
  const screen = screenFor(status);
  return screen === "workspace" ? `/decks/${id}` : `/decks/${id}/${screen}`;
}

/**
 * Sends the browser to the right screen when a deck is opened on a screen that does not fit its status
 * (for example the workspace of a deck whose outline is not approved yet).
 * Returns true while a redirect is on its way, so the caller can keep showing a loading state.
 */
export function useDeckGate(deck: Deck | undefined, here: DeckScreen, allowBuilding = false): boolean {
  const router = useRouter();
  let target: string | null = null;
  if (deck) {
    const want = screenFor(deck.status);
    const fits =
      want === here ||
      // Review and export are part of a finished deck.
      (want === "workspace" && (here === "review" || here === "export")) ||
      // "Open finished slides" lets the workspace show a deck that is still building.
      (allowBuilding && here === "workspace" && deck.status === "building");
    if (!fits) target = deckHref(deck.id, deck.status);
  }
  useEffect(() => {
    if (target) router.replace(target);
  }, [target, router]);
  return target !== null;
}
