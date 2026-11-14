// DEVELOPMENT MOCK ONLY (`pnpm dev:mock`). An in-memory imitation of the API in docs/SPEC.md,
// with timers standing in for the agents. State is lost when the dev server restarts.

import type {
  AskBody, Connection, CreateDeckBody, CriticReport, Deck, DeckSummary, ExportResult, Finding, FindingAction,
  Message, Node, OutlineBody, RenderedSlide, Routing, Rule, Slide, SlidePatch,
} from "@/lib/types";
import * as fx from "./fixtures";
import { place } from "./place";

export class MockError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

type Listener = (event: string, data: unknown) => void;
type FileEntry = { filename: string; body: string };

type State = {
  decks: Map<string, Deck & { paused: boolean; error: string | null }>;
  messages: Map<string, Message[]>;
  findings: Map<string, Finding[]>;
  versions: Map<string, Slide[]>; // slide id -> earlier snapshots
  rules: Rule[];
  connections: Connection[];
  routing: Routing;
  files: Map<string, FileEntry>;
  listeners: Map<string, Set<Listener>>;
  seq: number;
};

const g = globalThis as unknown as { __lecternMock?: State };

function init(): State {
  const s: State = {
    decks: new Map(), messages: new Map(), findings: new Map(), versions: new Map(),
    rules: fx.rules(), connections: fx.connections(), routing: fx.routing(), files: new Map(), listeners: new Map(), seq: 1,
  };
  const q3 = { ...fx.q3Deck(), paused: false, error: null };
  s.decks.set(q3.id, q3);
  s.messages.set(q3.id, fx.q3Messages());
  s.findings.set(q3.id, fx.q3Findings());
  return s;
}

const state: State = (g.__lecternMock ??= init());
let seeded = false;

/** Two more decks so Home shows every status: one waiting for approval, one mid-build. */
function seedOnce() {
  if (seeded || state.decks.size > 1) {
    seeded = true;
    return;
  }
  seeded = true;
  const offsite = newDeck({ prompt: "Team offsite agenda for three days in Lisbon: plan, build, decide.", slide_count: 6 }, "Team offsite agenda");
  writeOutline(offsite.id);
  const pitch = newDeck({ prompt: "Series A pitch for Northwind, a meal-kit startup raising $8M.", slide_count: 10 }, "Series A pitch · Northwind");
  writeOutline(pitch.id);
  approve(pitch.id);
}

const now = () => new Date().toISOString();
const uid = (p: string) => `${p}-${(state.seq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

function emit(deckId: string, event: string, data: unknown) {
  state.listeners.get(deckId)?.forEach((fn) => fn(event, data));
}

export function subscribe(deckId: string, fn: Listener): () => void {
  if (!state.listeners.has(deckId)) state.listeners.set(deckId, new Set());
  state.listeners.get(deckId)!.add(fn);
  return () => state.listeners.get(deckId)?.delete(fn);
}

function deck(id: string) {
  seedOnce();
  const d = state.decks.get(id);
  if (!d) throw new MockError(404, "That deck does not exist. It may have been deleted.");
  return d;
}

function slideOf(d: Deck, sid: string): Slide {
  const s = d.slides.find((x) => x.id === sid);
  if (!s) throw new MockError(404, "That slide is not in this deck.");
  return s;
}

const progress = (d: Deck) => ({ ready: d.slides.filter((s) => s.status === "ready").length, total: d.slides.length });

function touch(d: Deck) {
  d.updated_at = now();
  emit(d.id, "deck.updated", { status: d.status, progress: progress(d) });
}

function view(d: Deck) {
  return { ...clone(d), progress: progress(d) };
}

function run(deckId: string, role: string, slideIndex: number | null, status: string, summary: string, id = uid("run")) {
  emit(deckId, "run.updated", { id, role, slide_index: slideIndex, status, summary });
  return id;
}

/* ---------- decks ---------- */

export function listDecks(): DeckSummary[] {
  seedOnce();
  return [...state.decks.values()]
    .map((d) => ({ id: d.id, title: d.title, status: d.status, slide_count: d.slides.length, updated_at: d.updated_at, progress: progress(d), icon: (d as { icon?: string | null }).icon ?? null, icon_color: (d as { icon_color?: string | null }).icon_color ?? null }))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

function newDeck(body: CreateDeckBody, title = "New deck") {
  const d = {
    id: uid("deck"), title, status: "draft" as const,
    brief: { prompt: body.prompt, audience: body.audience, goal: body.goal, minutes: body.minutes, tone: body.tone },
    theme: fx.THEME, slides: [] as Slide[], created_at: now(), updated_at: now(), paused: false, error: null,
    slide_count: body.slide_count ?? 8,
  };
  state.decks.set(d.id, d);
  state.messages.set(d.id, []);
  state.findings.set(d.id, []);
  return d;
}

function writeOutline(id: string, shorter = false) {
  const d = state.decks.get(id);
  if (!d) return;
  const wanted = (d as unknown as { slide_count: number }).slide_count ?? 8;
  const count = shorter ? Math.max(3, Math.ceil((d.slides.length || wanted) * 0.7)) : wanted;
  const outline = fx.genericOutline(d.brief.prompt, count);
  if (d.title === "New deck") d.title = outline.title;
  d.slides = outline.rows.map((r, i) => ({
    id: uid("s"), index: i + 1, section: r.section, headline: i === 0 ? d.title : r.headline, layout: r.layout,
    nodes: [], notes: "", status: "queued" as const,
  }));
  d.status = "outline_ready";
  touch(d);
  emit(id, "outline.ready", {});
}

export function createDeck(body: CreateDeckBody) {
  if (!body?.prompt?.trim()) throw new MockError(422, "Say what the deck is about first.");
  seedOnce();
  const d = newDeck(body);
  const rid = run(d.id, "strategist", null, "running", "Reading your brief and drafting the outline.");
  setTimeout(() => {
    writeOutline(d.id);
    run(d.id, "strategist", null, "done", `Drafted an outline of ${state.decks.get(d.id)?.slides.length ?? 0} slides.`, rid);
  }, 2500);
  return view(d);
}

export const getDeck = (id: string) => view(deck(id));

export function patchDeck(id: string, body: { title?: string; icon?: string | null; icon_color?: string | null }) {
  const d = deck(id) as ReturnType<typeof deck> & { icon?: string | null; icon_color?: string | null };
  if (body.title !== undefined && body.title.trim()) d.title = body.title.trim();
  if (body.icon !== undefined) d.icon = body.icon || null;
  if (body.icon_color !== undefined) d.icon_color = body.icon_color || null;
  touch(d);
  return view(d);
}

export function deleteDeck(id: string) {
  deck(id);
  state.decks.delete(id);
  return { ok: true };
}

export function putOutline(id: string, body: OutlineBody) {
  const d = deck(id);
  if (d.status !== "outline_ready") throw new MockError(409, "The outline can only be changed before the deck is built.");
  if (!body.slides?.length) throw new MockError(422, "An outline needs at least one slide.");
  d.title = body.title?.trim() || d.title;
  d.slides = body.slides.map((r, i) => {
    const old = r.id ? d.slides.find((s) => s.id === r.id) : undefined;
    return {
      id: old?.id ?? uid("s"), index: i + 1, section: r.section ?? old?.section ?? "", headline: r.headline, layout: r.layout,
      nodes: [], notes: "", status: "queued" as const,
    };
  });
  touch(d);
  return view(d);
}

export function regenerate(id: string, instruction?: string) {
  const d = deck(id);
  if (d.status !== "outline_ready" && d.status !== "draft") throw new MockError(409, "This deck is already being built.");
  d.status = "draft";
  touch(d);
  const rid = run(id, "strategist", null, "running", instruction ? `Redrafting the outline: ${instruction}.` : "Redrafting the outline.");
  setTimeout(() => {
    writeOutline(id, /short/i.test(instruction ?? ""));
    run(id, "strategist", null, "done", "The new outline is ready.", rid);
  }, 2200);
  return view(d);
}

/* ---------- build ---------- */

function step(id: string, sid: string, phase: number) {
  const d = state.decks.get(id);
  const s = d?.slides.find((x) => x.id === sid);
  if (!d || !s || d.status !== "building") return;
  if (d.paused) {
    setTimeout(() => step(id, sid, phase), 500);
    return;
  }
  const set = (status: Slide["status"]) => {
    s.status = status;
    emit(id, "slide.updated", { slide_id: s.id, index: s.index, status, score: s.score });
  };
  const next = (ms: number) => setTimeout(() => step(id, sid, phase + 1), ms);
  const sendBack = s.index === 3; // one slide always takes the detour so the state can be seen
  switch (phase) {
    case 0:
      set("writing");
      run(id, "writer", s.index, "running", `Writing slide ${s.index}, “${s.headline}”.`, `${sid}-w`);
      next(1400);
      break;
    case 1: {
      const filled = fx.genericNodes(s.layout, s.headline);
      s.nodes = filled.nodes;
      s.notes = filled.notes;
      run(id, "writer", s.index, "done", `Wrote slide ${s.index} and its speaker notes.`, `${sid}-w`);
      run(id, "art_director", s.index, "done", `Kept the ${s.layout.replace(/_/g, " ")} layout for slide ${s.index}.`, `${sid}-a`);
      set("rendering");
      run(id, "renderer", s.index, "running", `Drawing slide ${s.index} as editable objects.`, `${sid}-r`);
      next(1100);
      break;
    }
    case 2:
      run(id, "renderer", s.index, "done", `Slide ${s.index} is drawn.`, `${sid}-r`);
      set("checking");
      run(id, "critic", s.index, "running", `Checking slide ${s.index} for overflow, small text and long lists.`, `${sid}-c`);
      next(1100);
      break;
    case 3:
      if (sendBack) {
        set("sent_back");
        run(id, "critic", s.index, "failed", `On slide ${s.index} the headline runs past its box. Sent it back to the Writer.`, `${sid}-c`);
        run(id, "writer", s.index, "running", `Shortening the headline on slide ${s.index}.`, `${sid}-w2`);
        next(1800);
      } else step(id, sid, 4);
      break;
    default: {
      if (sendBack) run(id, "writer", s.index, "done", `Shortened the headline on slide ${s.index}.`, `${sid}-w2`);
      s.score = 100;
      set("ready");
      run(id, "critic", s.index, "done", `Slide ${s.index} passed its checks.`, sendBack ? `${sid}-c2` : `${sid}-c`);
      const queued = d.slides.find((x) => x.status === "queued");
      if (queued) step(id, queued.id, 0);
      if (d.slides.every((x) => x.status === "ready")) {
        d.status = "ready";
        state.findings.set(id, lint(d));
      }
      touch(d);
    }
  }
}

export function approve(id: string) {
  const d = deck(id);
  if (d.status !== "outline_ready" && d.status !== "failed") throw new MockError(409, "This deck is not waiting for approval.");
  if (!d.slides.length) throw new MockError(422, "The outline is empty. Add a slide first.");
  d.status = "building";
  d.paused = false;
  d.slides.forEach((s) => {
    if (s.status !== "ready") s.status = "queued";
  });
  touch(d);
  run(id, "strategist", null, "done", `Locked the order you approved. ${d.slides.length} slides.`);
  // Three slides at a time, as in the spec.
  d.slides.filter((s) => s.status === "queued").slice(0, 3).forEach((s, i) => {
    s.status = "writing";
    setTimeout(() => step(id, s.id, 0), 300 + i * 500);
  });
  return view(d);
}

export function setPaused(id: string, paused: boolean) {
  const d = deck(id);
  if (d.status !== "building") throw new MockError(409, "This deck is not being built right now.");
  d.paused = paused;
  touch(d);
  return view(d);
}

/* ---------- slides ---------- */

function drawable(s: Slide) {
  return s.nodes.length > 0;
}

export function render(id: string): RenderedSlide[] {
  const d = deck(id);
  return d.slides.filter(drawable).map((s) => place(s, d.theme));
}

export function renderSlide(id: string, sid: string): RenderedSlide {
  const d = deck(id);
  return place(slideOf(d, sid), d.theme);
}

function snapshot(s: Slide): string {
  if (!state.versions.has(s.id)) state.versions.set(s.id, []);
  state.versions.get(s.id)!.push(clone(s));
  return `${s.id}-v${state.versions.get(s.id)!.length}`;
}

function syncHeadline(s: Slide, from: "headline" | "nodes") {
  const i = s.nodes.findIndex((n) => n.type === "text" && n.role === "headline");
  if (from === "headline") {
    const node: Node = { type: "text", role: "headline", value: s.headline };
    if (i >= 0) s.nodes[i] = node;
    else s.nodes.unshift(node);
  } else if (i >= 0) {
    const n = s.nodes[i];
    if (n.type === "text") s.headline = n.value;
  }
}

export function patchSlide(id: string, sid: string, patch: SlidePatch) {
  const d = deck(id);
  const s = slideOf(d, sid);
  snapshot(s);
  if (patch.nodes) {
    s.nodes = patch.nodes;
    syncHeadline(s, "nodes");
  }
  if (patch.headline !== undefined) {
    s.headline = patch.headline;
    syncHeadline(s, "headline");
  }
  if (patch.layout) s.layout = patch.layout;
  if (patch.notes !== undefined) s.notes = patch.notes;
  if (d.status === "ready") relint(d);
  touch(d);
  emit(id, "slide.updated", { slide_id: s.id, index: s.index, status: s.status, score: s.score });
  return clone(s);
}

export function undoSlide(id: string, sid: string) {
  const d = deck(id);
  const s = slideOf(d, sid);
  const prev = state.versions.get(sid)?.pop();
  if (!prev) throw new MockError(409, "There is nothing to undo on this slide.");
  Object.assign(s, prev, { index: s.index });
  if (d.status === "ready") relint(d);
  touch(d);
  emit(id, "slide.updated", { slide_id: s.id, index: s.index, status: s.status, score: s.score });
  return clone(s);
}

/* ---------- ask ---------- */

function applyAsk(s: Slide, text: string): string {
  if (/short/i.test(text)) {
    const words = s.headline.split(/\s+/);
    if (words.length <= 6) return `The headline on slide ${s.index} is already short.`;
    snapshot(s);
    s.headline = words.slice(0, 6).join(" ").replace(/[,;:]$/, "");
    syncHeadline(s, "headline");
    return `Cut the headline on slide ${s.index} to six words.`;
  }
  if (/source/i.test(text)) {
    snapshot(s);
    const stat = s.nodes.find((n) => n.type === "stat");
    if (stat && stat.type === "stat") stat.source = "Source: company data, Q3";
    else s.nodes.push({ type: "text", role: "caption", value: "Source: company data, Q3" });
    return `Added a source line to slide ${s.index}.`;
  }
  if (/layout/i.test(text)) {
    snapshot(s);
    s.layout = s.layout === "two_column" ? "bullets" : "two_column";
    return `Switched slide ${s.index} to the ${s.layout.replace(/_/g, " ")} layout.`;
  }
  snapshot(s);
  s.notes = `${s.notes}${s.notes ? "\n\n" : ""}Requested change: ${text}`;
  return `The mock editor cannot rewrite slides. It added your request to the speaker notes of slide ${s.index} so there is a change to see and undo.`;
}

export function ask(id: string, body: AskBody) {
  deck(id);
  if (!body?.message?.trim()) throw new MockError(422, "Type what you would like changed.");
  if (body.scope === "slide" && !body.slide_id) throw new MockError(422, "Pick a slide first.");
  const m: Message = {
    id: uid("msg"), role: "user", scope: body.scope, slide_id: body.scope === "slide" ? body.slide_id : null,
    text: body.message.trim(), status: "pending", result: null, version_ids: [], changed_slide_ids: [], created_at: now(),
  };
  state.messages.get(id)!.push(m);
  const rid = run(id, "editor", null, "running", `Working on: ${m.text}`);
  setTimeout(() => {
    const live = state.decks.get(id);
    if (!live) return;
    const targets = m.scope === "slide" ? live.slides.filter((s) => s.id === m.slide_id) : live.slides.filter(drawable);
    const before = targets.map((s) => JSON.stringify(s));
    const results = targets.map((s) => applyAsk(s, m.text));
    m.changed_slide_ids = targets.filter((s, i) => JSON.stringify(s) !== before[i]).map((s) => s.id);
    m.version_ids = m.changed_slide_ids.map((sid) => `v-${sid}`);
    m.result = m.scope === "slide" ? (results[0] ?? "That slide is gone.") : `Went through ${targets.length} slides and changed ${m.changed_slide_ids.length}.`;
    m.status = "done";
    if (live.status === "ready") relint(live);
    touch(live);
    emit(id, "message.updated", { id: m.id, status: m.status, result: m.result });
    run(id, "editor", null, "done", String(m.result), rid);
  }, 2000);
  return { message_id: m.id };
}

/** Mock Ask undo: steps each changed slide back once (the server reverts exactly the Ask's versions). */
export function undoMessage(id: string, mid: string) {
  const m = (state.messages.get(id) ?? []).find((x) => x.id === mid);
  if (!m) throw new MockError(404, "That request does not exist in this deck.");
  if (m.undone) throw new MockError(409, "Those changes were already undone.");
  const reverted = (m.changed_slide_ids ?? []).filter((sid) => {
    try { undoSlide(id, sid); return true; } catch { return false; }
  });
  m.undone = true;
  return { reverted_slide_ids: reverted, kept: [] };
}

export const getMessages = (id: string) => (deck(id), clone(state.messages.get(id) ?? []));

/* ---------- critic ---------- */

const words = (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0);

function lint(d: Deck): Finding[] {
  const out: Finding[] = [];
  const add = (s: Slide, rule: string, severity: Finding["severity"], title: string, detail: string) =>
    out.push({ id: `${s.id}-${rule}`, slide_id: s.id, slide_index: s.index, rule, severity, title, detail, status: "open" });
  for (const s of d.slides) {
    if (words(s.headline) > 12) add(s, "long_headline", "medium", `The headline on slide ${s.index} is ${words(s.headline)} words long`, "Twelve words is about the most a room reads at a glance.");
    for (const n of s.nodes) if (n.type === "bullets" && n.items.length > 5) add(s, "too_many_bullets", "medium", `Slide ${s.index} has ${n.items.length} bullets`, "A room reads about four. I would keep the strongest four.");
    if (!s.notes.trim()) add(s, "missing_notes", "low", `Slide ${s.index} has no speaker notes`, "A sentence to say out loud helps on the day.");
  }
  return out;
}

/** Re-run the deterministic checks after an edit, keeping decisions already made. */
function relint(d: Deck) {
  const old = state.findings.get(d.id) ?? [];
  if (d.id === "q3-board-review") {
    // Fixture findings are hand-written; only close the ones an edit has clearly resolved.
    for (const f of old) {
      const s = d.slides.find((x) => x.id === f.slide_id);
      if (!s || f.status !== "open") continue;
      if (f.rule === "missing_notes" && s.notes.trim()) f.status = "fixed";
      if (f.rule === "number_mismatch" && !s.notes.includes("4.2%")) f.status = "fixed";
      if (f.rule === "too_many_bullets" && !s.nodes.some((n) => n.type === "bullets" && n.items.length > 5)) f.status = "fixed";
    }
    return;
  }
  const fresh = lint(d);
  for (const f of fresh) {
    const prev = old.find((o) => o.id === f.id);
    if (prev && prev.status === "kept") f.status = "kept";
  }
  for (const o of old) if (o.status === "fixed" && !fresh.some((f) => f.id === o.id)) fresh.push(o);
  state.findings.set(d.id, fresh);
}

export function critic(id: string): CriticReport {
  const d = deck(id);
  const findings = clone(state.findings.get(id) ?? []).sort((a, b) => a.slide_index - b.slide_index);
  const cost = { high: 12, medium: 6, low: 3 } as const;
  const open = findings.filter((f) => f.status === "open");
  const total = Math.max(1, d.slides.length);
  const score = (list: Finding[]) => Math.max(0, Math.round(100 - list.reduce((a, f) => a + cost[f.severity], 0) / total * 4));
  const story = open.filter((f) => /headline|notes|number|claim/.test(f.rule));
  const design = open.filter((f) => !/headline|notes|number|claim/.test(f.rule));
  for (const s of d.slides) s.score = Math.max(0, 100 - open.filter((f) => f.slide_id === s.id).reduce((a, f) => a + cost[f.severity], 0));
  return { score: Math.round(d.slides.reduce((a, s) => a + (s.score ?? 100), 0) / total), story: score(story), design: score(design), editability: 100, findings };
}

function fix(d: Deck, f: Finding) {
  const s = d.slides.find((x) => x.id === f.slide_id);
  if (!s) return;
  snapshot(s);
  if (f.rule === "too_many_bullets") s.nodes = s.nodes.map((n) => (n.type === "bullets" ? { ...n, items: n.items.slice(0, 4) } : n));
  if (f.rule === "long_headline") {
    s.headline = s.headline.split(/\s+/).slice(0, 10).join(" ");
    syncHeadline(s, "headline");
  }
  if (f.rule === "missing_notes") s.notes = `Say the headline: ${s.headline}. Then ask for the decision.`;
  if (f.rule === "number_mismatch") s.notes = s.notes.replace("4.2%", "4.1%");
  if (f.rule === "empty_slot") s.nodes = s.nodes.map((n) => (n.type === "stat" ? { ...n, source: "Source: Q4 retention plan, finance" } : n));
  emit(d.id, "slide.updated", { slide_id: s.id, index: s.index, status: s.status });
}

export function actOnFinding(id: string, fid: string, action: FindingAction) {
  const d = deck(id);
  const f = (state.findings.get(id) ?? []).find((x) => x.id === fid);
  if (!f) throw new MockError(404, "That finding no longer exists.");
  if (action === "fix") {
    fix(d, f);
    f.status = "fixed";
  } else if (action === "keep") {
    f.status = "kept";
    state.rules.push({ id: uid("r"), text: `Keep as is: ${f.title}`, created_at: now(), source: `Kept a finding on ${d.title}` });
  } else f.status = "open";
  touch(d);
  emit(id, "finding.updated", { id: f.id, status: f.status });
  return clone(f);
}

export function fixAll(id: string) {
  const d = deck(id);
  for (const f of state.findings.get(id) ?? []) {
    if (f.status !== "open") continue;
    fix(d, f);
    f.status = "fixed";
    emit(id, "finding.updated", { id: f.id, status: f.status });
  }
  touch(d);
  return critic(id);
}

/* ---------- rules ---------- */

export const listRules = () => clone(state.rules);
export function addRule(text: string): Rule {
  if (!text?.trim()) throw new MockError(422, "Write the rule first.");
  const r = { id: uid("r"), text: text.trim(), created_at: now(), source: null };
  state.rules.push(r);
  return r;
}
export function deleteRule(rid: string) {
  if (!state.rules.some((r) => r.id === rid)) throw new MockError(404, "That rule is already gone.");
  state.rules = state.rules.filter((r) => r.id !== rid);
  return { ok: true };
}

/* ---------- export ---------- */

export function exportDeck(id: string, includeNotes: boolean): ExportResult {
  const d = deck(id);
  if (d.status !== "ready") throw new MockError(409, "The deck has to finish building before it can be exported.");
  const els = render(id).flatMap((r) => r.elements);
  const count = (k: string) => els.filter((e) => e.kind === k).length;
  const pictures = els.filter((e) => e.kind === "image" && e.src).length;
  const notes = includeNotes ? d.slides.filter((s) => s.notes.trim()).length : 0;
  const body = [
    "This is a stand-in file from the Lectern mock API.",
    "Run the real API (see web/README.md) to export an editable PowerPoint file.",
    "",
    ...d.slides.map((s) => `${s.index}. ${s.headline}${includeNotes && s.notes ? `\n   Notes: ${s.notes}` : ""}`),
  ].join("\n");
  const fileId = uid("file");
  const filename = `${d.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-mock.txt`;
  state.files.set(fileId, { filename, body });
  return {
    file_id: fileId, filename, bytes: Buffer.byteLength(body),
    report: {
      total_objects: els.length, editable_objects: els.length - pictures, pictures, charts: count("chart"), tables: count("table"),
      text_boxes: count("text"), notes_slides: notes,
      checks: [
        { label: `${count("chart")} charts are real PowerPoint charts`, detail: "Click a chart to edit its numbers", ok: true },
        { label: "All text is live text", detail: `${count("text")} text boxes, none saved as pictures`, ok: true },
        { label: `${count("table")} tables are real tables`, detail: "Rows and columns can be changed", ok: true },
        { label: includeNotes ? "Speaker notes included" : "Speaker notes left out", detail: includeNotes ? `Notes on ${notes} of ${d.slides.length} slides` : "You switched notes off", ok: includeNotes ? notes === d.slides.length : true },
        { label: "Mock export: the file is a text stand-in", detail: "The real API writes the .pptx", ok: false },
      ],
    },
  };
}

export function file(fileId: string): FileEntry {
  const f = state.files.get(fileId);
  if (!f) throw new MockError(404, "That file is no longer available. Export the deck again.");
  return f;
}

/* ---------- settings ---------- */

export const getConnections = () => clone(state.connections);

export function putConnection(body: { id?: string; api_key?: string; key?: string; base_url?: string }) {
  const c = state.connections.find((x) => x.id === body?.id);
  if (!c) throw new MockError(404, "That connection does not exist.");
  const key = body.api_key ?? body.key;
  if (key !== undefined) {
    c.has_key = key.trim().length > 0;
    c.status = c.has_key ? "connected" : "not_connected";
  }
  if (body.base_url !== undefined) c.base_url = body.base_url || null;
  return clone(state.connections);
}

export function testConnection(cid: string) {
  const c = state.connections.find((x) => x.id === cid);
  if (!c) throw new MockError(404, "That connection does not exist.");
  if (c.kind !== "offline" && !c.has_key && c.id !== "ollama")
    return { ok: false, detail: `${c.label} needs a key before it can be tested.` };
  return { ok: true, detail: `${c.label} answered. This is the mock API, so no real request was made.`, models: fx.MODELS[c.id] ?? [] };
}

const PRESETS = [
  { id: "best_quality", label: "Best quality", description: "Best quality uses the strongest connected model for every job." },
  { id: "balanced", label: "Balanced", description: "Balanced uses the strongest model only where it matters most." },
  { id: "lowest_cost", label: "Lowest cost", description: "Lowest cost uses the smallest model that can do each job." },
];

export const getRouting = () => ({ ...clone(state.routing), presets: PRESETS });

export function putRouting(body: Partial<Routing>) {
  if (body.roles) {
    state.routing = { preset: body.preset ?? "custom", roles: { ...state.routing.roles, ...body.roles } };
  } else if (body.preset) {
    const provider = state.connections.find((c) => c.status === "connected" && c.kind !== "offline")?.id ?? "offline";
    const models = fx.MODELS[provider] ?? ["offline-1"];
    const strong = models[0];
    const light = models[models.length - 1];
    const pick = (heavy: boolean) => ({ provider, model: body.preset === "best_quality" ? strong : body.preset === "lowest_cost" ? light : heavy ? strong : light });
    state.routing = {
      preset: body.preset,
      roles: { strategist: pick(true), writer: pick(true), art_director: pick(true), renderer: pick(false), critic: pick(false), editor: pick(true) },
    };
  }
  return getRouting();
}

export const health = () => ({ ok: true, provider: state.routing.roles.writer.provider });
export const layouts = () => fx.LAYOUTS;
