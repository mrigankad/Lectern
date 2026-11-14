"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, keys } from "./api";
import type { RunEvent } from "./types";

export type ActivityItem = RunEvent & { at: number };

const MAX_ACTIVITY = 40;

function parse<T>(e: Event): T | null {
  try {
    return JSON.parse((e as MessageEvent).data) as T;
  } catch {
    return null;
  }
}

/**
 * Subscribes to /api/decks/{id}/events and invalidates the query each event touches
 * (deck, render, critic, messages). `run.updated` events are also kept, newest first,
 * under keys.activity(id) so the activity feed survives moving between screens.
 * Returns whether the stream is connected right now.
 */
export function useDeckEvents(deckId: string | undefined, onOutlineReady?: () => void): boolean {
  const qc = useQueryClient();
  const [live, setLive] = useState(false);
  const outlineReady = useRef(onOutlineReady);
  useEffect(() => {
    outlineReady.current = onOutlineReady;
  });

  useEffect(() => {
    if (!deckId || typeof EventSource === "undefined") return;
    const id = deckId;
    const source = new EventSource(api.eventsUrl(id));
    const invalidate = (...ks: (readonly unknown[])[]) => ks.forEach((queryKey) => qc.invalidateQueries({ queryKey }));

    source.onopen = () => setLive(true);
    source.onerror = () => setLive(false); // EventSource reconnects by itself

    source.addEventListener("deck.updated", () => invalidate(keys.deck(id), keys.decks, keys.render(id)));
    source.addEventListener("outline.ready", () => {
      invalidate(keys.deck(id), keys.decks);
      outlineReady.current?.();
    });
    source.addEventListener("slide.updated", () => invalidate(keys.deck(id), keys.render(id)));
    source.addEventListener("message.updated", () =>
      invalidate(keys.messages(id), keys.deck(id), keys.render(id), keys.critic(id)),
    );
    source.addEventListener("finding.updated", () =>
      invalidate(keys.critic(id), keys.deck(id), keys.render(id), keys.rules),
    );
    source.addEventListener("run.updated", (e) => {
      const run = parse<RunEvent>(e);
      if (!run) return;
      qc.setQueryData<ActivityItem[]>(keys.activity(id), (old = []) => {
        const previous = old.find((item) => item.id === run.id);
        const rest = old.filter((item) => item.id !== run.id);
        return [{ ...run, at: previous?.at ?? Date.now() }, ...rest].slice(0, MAX_ACTIVITY);
      });
    });

    return () => {
      source.close();
      setLive(false);
    };
  }, [deckId, qc]);

  return live;
}
