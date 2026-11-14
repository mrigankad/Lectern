"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3, Banknote, BookOpen, Briefcase, Building2, Calendar, Compass, Cpu, FileText, Flag, FlaskConical,
  Globe, GraduationCap, Heart, Landmark, Layers, Lightbulb, Megaphone, Package, Palette, PieChart, Rocket,
  ShieldCheck, ShoppingBag, Sparkles, Target, TrendingUp, Trophy, Users, Wrench, type LucideIcon,
} from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, keys } from "@/lib/api";
import { cx } from "@/lib/format";
import type { DeckStatus, DeckSummary } from "@/lib/types";

export const DECK_ICONS: Record<string, { icon: LucideIcon; label: string }> = {
  chart: { icon: BarChart3, label: "Chart" },
  trend: { icon: TrendingUp, label: "Growth" },
  pie: { icon: PieChart, label: "Breakdown" },
  money: { icon: Banknote, label: "Money" },
  bank: { icon: Landmark, label: "Finance" },
  rocket: { icon: Rocket, label: "Launch" },
  target: { icon: Target, label: "Goal" },
  flag: { icon: Flag, label: "Milestone" },
  trophy: { icon: Trophy, label: "Win" },
  briefcase: { icon: Briefcase, label: "Business" },
  building: { icon: Building2, label: "Company" },
  users: { icon: Users, label: "Team" },
  megaphone: { icon: Megaphone, label: "Announcement" },
  bulb: { icon: Lightbulb, label: "Idea" },
  sparkles: { icon: Sparkles, label: "New" },
  compass: { icon: Compass, label: "Strategy" },
  layers: { icon: Layers, label: "Architecture" },
  cpu: { icon: Cpu, label: "Tech" },
  wrench: { icon: Wrench, label: "Engineering" },
  shield: { icon: ShieldCheck, label: "Security" },
  flask: { icon: FlaskConical, label: "Research" },
  cap: { icon: GraduationCap, label: "Lesson" },
  book: { icon: BookOpen, label: "Story" },
  doc: { icon: FileText, label: "Report" },
  calendar: { icon: Calendar, label: "Plan" },
  globe: { icon: Globe, label: "Market" },
  bag: { icon: ShoppingBag, label: "Sales" },
  package: { icon: Package, label: "Product" },
  palette: { icon: Palette, label: "Design" },
  heart: { icon: Heart, label: "Customers" },
};

/** Soft tile background + strong glyph colour, all from the house palette. */
export const DECK_COLORS: Record<string, { bg: string; fg: string; label: string }> = {
  blue: { bg: "var(--action-soft)", fg: "var(--action)", label: "Blue" },
  purple: { bg: "var(--ai-soft)", fg: "var(--ai-ink)", label: "Purple" },
  teal: { bg: "var(--teal-soft)", fg: "var(--teal)", label: "Teal" },
  green: { bg: "var(--pass-soft)", fg: "var(--pass)", label: "Green" },
  amber: { bg: "var(--warn-soft)", fg: "var(--warn)", label: "Amber" },
  red: { bg: "var(--fail-soft)", fg: "var(--fail)", label: "Red" },
  grey: { bg: "var(--surface-2)", fg: "var(--body)", label: "Grey" },
};

const COLOR_ORDER = ["blue", "purple", "teal", "green", "amber", "red", "grey"];

/** A sensible icon when the user has not chosen one, guessed from the title. */
function guessIcon(title: string): string {
  const t = title.toLowerCase();
  const rules: [RegExp, string][] = [
    [/pitch|series|investor|fundrais|seed/, "rocket"],
    [/board|quarter|q[1-4]\b|review|results/, "chart"],
    [/revenue|budget|finance|cost|price/, "money"],
    [/launch|release|product/, "package"],
    [/sales|deal|customer story|case study/, "bag"],
    [/team|hiring|all.hands|town hall|offsite/, "users"],
    [/lesson|class|course|training|teach|biology|thesis|lecture/, "cap"],
    [/strategy|plan|roadmap/, "compass"],
    [/architecture|system|migration|platform/, "layers"],
    [/security|risk|compliance/, "shield"],
    [/research|study|experiment/, "flask"],
    [/market|global/, "globe"],
    [/design|brand/, "palette"],
    [/update|status|report/, "doc"],
  ];
  return rules.find(([re]) => re.test(t))?.[1] ?? "doc";
}

const STATUS_COLOR: Record<DeckStatus, string> = {
  interview: "purple", draft: "purple", outline_ready: "amber", building: "blue", ready: "green", failed: "red",
};

export function resolveDeckIcon(d: Pick<DeckSummary, "title" | "status" | "icon" | "icon_color">) {
  const iconId = d.icon && DECK_ICONS[d.icon] ? d.icon : guessIcon(d.title || "");
  const colorId = d.icon_color && DECK_COLORS[d.icon_color] ? d.icon_color : STATUS_COLOR[d.status] ?? "grey";
  return { iconId, colorId, Icon: DECK_ICONS[iconId].icon, color: DECK_COLORS[colorId] };
}

export function DeckIconTile({ deck, size = 20 }: { deck: Pick<DeckSummary, "title" | "status" | "icon" | "icon_color">; size?: number }) {
  const { Icon, color } = resolveDeckIcon(deck);
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-[6px]"
      style={{ width: size, height: size, background: color.bg, color: color.fg }}
    >
      <Icon size={Math.round(size * 0.62)} strokeWidth={2} aria-hidden />
    </span>
  );
}

/** The deck icon in the sidebar: a button that opens an icon and colour picker. */
export function DeckIconPicker({ deck }: { deck: DeckSummary }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const { iconId, colorId } = resolveDeckIcon(deck);

  const save = useMutation({
    mutationFn: (body: { icon?: string | null; icon_color?: string | null }) => api.patchDeck(deck.id, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: keys.decks });
      const prev = qc.getQueryData<DeckSummary[]>(keys.decks);
      qc.setQueryData<DeckSummary[]>(keys.decks, (list) => list?.map((d) => (d.id === deck.id ? { ...d, ...body } : d)));
      return { prev };
    },
    onError: (_e, _b, ctx) => ctx?.prev && qc.setQueryData(keys.decks, ctx.prev),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.decks });
      qc.invalidateQueries({ queryKey: keys.deck(deck.id) });
    },
  });

  useLayoutEffect(() => {
    if (!open) return;
    const r = btn.current?.getBoundingClientRect();
    if (r) setPos({ left: r.right + 10, top: Math.max(8, Math.min(r.top - 8, window.innerHeight - 340)) });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (btn.current?.contains(e.target as Node) || panel.current?.contains(e.target as Node)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && (setOpen(false), btn.current?.focus());
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={btn}
        type="button"
        aria-label={`Change icon for ${deck.title || "this deck"}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Change icon"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="rounded-[6px] transition-transform hover:scale-110"
      >
        <DeckIconTile deck={deck} size={20} />
      </button>
      {open && pos
        ? createPortal(
            <div
              ref={panel}
              role="dialog"
              aria-label="Deck icon"
              className="dropdown-menu fixed z-50 w-[272px] rounded-card border border-line bg-bg p-3"
              style={{ left: pos.left, top: pos.top }}
            >
              <div className="flex items-center justify-between pb-2">
                <span className="text-[13px] font-bold text-ink">Deck icon</span>
                {deck.icon || deck.icon_color ? (
                  <button
                    type="button"
                    onClick={() => save.mutate({ icon: null, icon_color: null })}
                    className="text-[12px] font-bold text-action hover:underline"
                  >
                    Reset
                  </button>
                ) : null}
              </div>
              <div className="flex gap-1.5 pb-3" role="radiogroup" aria-label="Colour">
                {COLOR_ORDER.map((c) => (
                  <button
                    key={c}
                    type="button"
                    role="radio"
                    aria-checked={c === colorId}
                    aria-label={DECK_COLORS[c].label}
                    title={DECK_COLORS[c].label}
                    onClick={() => save.mutate({ icon_color: c })}
                    className={cx(
                      "size-6 rounded-pill border-2 transition-transform hover:scale-110",
                      c === colorId ? "border-action" : "border-transparent",
                    )}
                    style={{ background: DECK_COLORS[c].fg }}
                  />
                ))}
              </div>
              <div className="scroll-thin grid max-h-[230px] grid-cols-6 gap-1 overflow-y-auto" role="radiogroup" aria-label="Icon">
                {Object.entries(DECK_ICONS).map(([id, { icon: Icon, label }]) => (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={id === iconId}
                    aria-label={label}
                    title={label}
                    onClick={() => save.mutate({ icon: id })}
                    className={cx(
                      "flex size-9 items-center justify-center rounded-control transition-colors",
                      id === iconId ? "ring-2 ring-action" : "hover:bg-surface-2",
                    )}
                    style={id === iconId ? { background: DECK_COLORS[colorId].bg, color: DECK_COLORS[colorId].fg } : undefined}
                  >
                    <Icon size={17} aria-hidden className={id === iconId ? undefined : "text-body"} />
                  </button>
                ))}
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
