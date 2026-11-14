import type { LayoutId } from "./types";

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "3 min ago", "yesterday", "12 Aug". */
export function timeAgo(iso: string | number, now = Date.now()): string {
  const t = typeof iso === "number" ? iso : new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 10) return "just now";
  if (s < 60) return `${s} sec ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} ${h === 1 ? "hour" : "hours"} ago`;
  const d = Math.round(h / 24);
  if (d === 1) return "yesterday";
  if (d < 7) return `${d} days ago`;
  return new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

/** Speaking time at about 150 words a minute. */
export function sayTime(text: string): string {
  const words = wordCount(text);
  if (!words) return "No notes yet";
  const seconds = Math.max(5, Math.round(((words / 150) * 60) / 5) * 5);
  if (seconds < 90) return `About ${seconds} seconds to say`;
  return `About ${Math.round(seconds / 60)} minutes to say`;
}

/** Rough talk time used on the outline screen: a minute and a half a slide. */
export const MINUTES_PER_SLIDE = 1.5;
export function talkMinutes(slides: number): number {
  return Math.max(1, Math.round(slides * MINUTES_PER_SLIDE));
}

export const LAYOUT_NAMES: Record<LayoutId, string> = {
  title: "Title",
  agenda: "Agenda",
  section: "Section",
  big_idea: "Big idea",
  bullets: "List",
  two_column: "Two column",
  three_column: "Three column",
  process: "Process",
  timeline: "Timeline",
  chart: "Chart",
  dashboard: "Dashboard",
  table: "Table",
  quote: "Quote",
  case_study: "Case study",
  diagram: "Diagram",
  team: "Team",
  summary: "Summary",
  next_steps: "Next steps",
  closing: "Closing",
  appendix: "Appendix",
  big_number: "Big number",
};
export const LAYOUT_IDS = Object.keys(LAYOUT_NAMES) as LayoutId[];

export function layoutName(id: string): string {
  return LAYOUT_NAMES[id as LayoutId] ?? id.replace(/_/g, " ");
}

const ROLE_NAMES: Record<string, string> = {
  strategist: "Strategist",
  writer: "Writer",
  art_director: "Art Director",
  renderer: "Renderer",
  critic: "Critic",
  editor: "Editor",
  analyst: "Analyst",
};
export function roleName(role: string): string {
  return ROLE_NAMES[role] ?? role.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

const PROVIDER_NAMES: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  openai_compatible: "OpenAI-compatible",
  openrouter: "OpenRouter",
  gemini: "Gemini",
  ollama: "Ollama",
  offline: "Offline",
};
export function providerName(id: string): string {
  return PROVIDER_NAMES[id] ?? id.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function greeting(hour: number): string {
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
