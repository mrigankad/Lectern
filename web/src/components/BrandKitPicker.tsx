"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Palette } from "lucide-react";
import { Dropdown, InlineError, Pill } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import type { Deck } from "@/lib/types";

/** Workspace Design tab: choose the deck's brand kit and see how well the deck follows it. */
export function BrandKitPicker({ deck }: { deck: Deck }) {
  const qc = useQueryClient();
  const kits = useQuery({ queryKey: keys.brandKits, queryFn: api.listBrandKits });
  const current = deck.theme?.brand_kit_id ?? "none";
  const match = useQuery({
    queryKey: [...keys.brandMatch(deck.id), deck.updated_at, current],
    queryFn: () => api.brandMatch(deck.id),
    enabled: current !== "none",
  });
  const apply = useMutation({
    mutationFn: (value: string) => api.setDeckBrandKit(deck.id, value === "none" ? null : value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.deck(deck.id) });
      qc.invalidateQueries({ queryKey: keys.render(deck.id) });
      qc.invalidateQueries({ queryKey: keys.critic(deck.id) });
      qc.invalidateQueries({ queryKey: keys.brandMatch(deck.id) });
      qc.invalidateQueries({ queryKey: keys.brandKits });
    },
  });
  const options = [{ value: "none", label: "Lectern default" }, ...(kits.data ?? []).map((k) => ({ value: k.id, label: k.name }))];
  const label = options.find((o) => o.value === current)?.label ?? "Lectern default";
  const failing = (match.data?.rules ?? []).filter((r) => r.checkable && r.enabled && !r.passed);
  const score = match.data?.score;

  return (
    <div className="flex flex-col gap-2.5 border-b border-line p-4">
      <div className="flex flex-col gap-0.5">
        <h2 className="text-[17px] font-bold leading-6 text-ink">Brand kit</h2>
        <p className="text-[13px] leading-[19px] text-body">
          Colours, font and logo come from the kit. The PowerPoint file is built on its template.
        </p>
      </div>
      <Dropdown value={current} options={options} onChange={(v) => v !== current && apply.mutate(v)} ariaLabel="Brand kit" disabled={apply.isPending}>
        <span className="flex shrink-0 text-body"><Palette size={16} /></span>
        <span className="truncate font-bold text-ink">{label}</span>
      </Dropdown>
      <InlineError>{apply.isError ? errorText(apply.error) : null}</InlineError>
      {kits.data && kits.data.length === 0 ? (
        <p className="text-[13px] leading-[19px] text-body">
          No brand kits yet. <Link href="/brand-kits" className="font-bold text-action hover:underline">Upload a template</Link>
        </p>
      ) : null}
      {current !== "none" && typeof score === "number" ? (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[13px] text-body">Brand match</span>
            <Pill tone={score >= 90 ? "pass" : score >= 70 ? "warn" : "fail"}>{score} / 100</Pill>
          </div>
          {failing.slice(0, 3).map((r) => (
            <p key={r.id} className="text-[12px] leading-[17px] text-body">
              <span className="font-bold text-ink">{r.text}</span>: slide {r.failing.slice(0, 4).map((f) => f.slide_index).join(", ")}
              {r.failing.length > 4 ? " and more" : ""}
            </p>
          ))}
          <Link href={`/brand-kits/${current}`} className="text-[13px] font-bold text-action hover:underline">Edit the brand rules</Link>
        </div>
      ) : null}
    </div>
  );
}
