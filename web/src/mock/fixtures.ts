// DEVELOPMENT MOCK ONLY. Fixture data for `pnpm dev:mock`.

import type { Connection, Deck, Finding, LayoutId, LayoutInfo, Message, Node, Routing, Rule, Slide, Theme } from "@/lib/types";

export const THEME: Theme = {
  name: "Neutral",
  font: "Urbanist",
  colors: { bg: "#FFFFFF", ink: "#16181D", body: "#5E6370", muted: "#7A7F8C", line: "#E8E8EC", surface: "#F7F7F8", accent: "#2563EB", on_accent: "#FFFFFF" },
  chart_colors: ["#16181D", "#2563EB", "#7A7F8C", "#0E8F8E", "#7C5CFF", "#B87400"],
};

const iso = (minutesAgo: number) => new Date(Date.now() - minutesAgo * 60_000).toISOString();
const head = (value: string): Node => ({ type: "text", role: "headline", value });

type Draft = { section: string; headline: string; layout: LayoutId; nodes: Node[]; notes: string };

function slides(prefix: string, drafts: Draft[], status: Slide["status"] = "ready"): Slide[] {
  return drafts.map((d, i) => ({
    id: `${prefix}-s${i + 1}`,
    index: i + 1,
    section: d.section,
    headline: d.headline,
    layout: d.layout,
    nodes: [head(d.headline), ...d.nodes],
    notes: d.notes,
    status,
    score: status === "ready" ? 100 : undefined,
  }));
}

const Q3: Draft[] = [
  {
    section: "Opening", headline: "Q3 was our best quarter, with one crack in it", layout: "title",
    nodes: [{ type: "text", role: "eyebrow", value: "Board review · October 2026" }, { type: "text", role: "subhead", value: "Revenue is up 34%. Churn is the thing to talk about." }],
    notes: "Welcome everyone. The short version: the quarter was strong, and there is one number I want us to spend most of our time on.",
  },
  {
    section: "Opening", headline: "Three decisions we need from you today", layout: "agenda",
    nodes: [{ type: "bullets", items: ["Approve a $1.2M retention budget for Q4", "Agree the churn target: back under 3% by February", "Back onboarding as the first fix, ahead of pricing"] }],
    notes: "These are the three things I will ask for at the end. Everything in between is the evidence.",
  },
  {
    section: "Where we are", headline: "Revenue grew 34%, ahead of plan", layout: "big_number",
    nodes: [
      { type: "text", role: "eyebrow", value: "Revenue" },
      { type: "stat", value: "34%", caption: "Revenue growth, quarter on quarter", source: "Source: q3-financials, sheet 1" },
      { type: "chart", kind: "bar", title: "Revenue by quarter, $M", categories: ["Q4", "Q1", "Q2", "Q3"], series: [{ name: "Revenue", values: [3.1, 3.6, 4.1, 5.5] }], unit: "$" },
    ],
    notes: "Revenue grew 34% against a plan of 26%. This is the third quarter in a row ahead of plan.",
  },
  {
    section: "Where we are", headline: "New customers carried the quarter, not upgrades", layout: "chart",
    nodes: [{ type: "chart", kind: "bar", categories: ["Q4", "Q1", "Q2", "Q3"], series: [{ name: "New customers", values: [0.9, 1.3, 1.8, 2.6] }, { name: "Upgrades", values: [0.5, 0.55, 0.6, 0.65] }], unit: "$" }],
    notes: "Almost all of the growth came from new logos. Upgrade revenue was nearly flat, which matters later.",
  },
  {
    section: "Where we are", headline: "Enterprise is now half of new revenue", layout: "two_column",
    nodes: [
      { type: "stat", value: "51%", caption: "of new revenue came from enterprise accounts" },
      { type: "chart", kind: "pie", categories: ["Enterprise", "Mid-market", "Small business"], series: [{ name: "Share of new revenue", values: [51, 31, 18] }] },
    ],
    notes: "Enterprise crossed half of new revenue for the first time. These accounts also churn the least.",
  },
  {
    section: "Where we are", headline: "We shipped everything we promised in Q2", layout: "timeline",
    nodes: [{ type: "items", style: "timeline", items: [
      { label: "July", title: "Single sign-on", body: "Live for all enterprise plans" },
      { label: "August", title: "Usage reports", body: "Weekly digest for admins" },
      { label: "September", title: "Guided setup", body: "Pilot with 40 accounts" },
      { label: "September", title: "Audit log", body: "Closed three enterprise deals" },
    ] }],
    notes: "Four commitments, four delivered. Guided setup is the one to remember, because it comes back in the ask.",
  },
  {
    section: "The risk", headline: "Churn is the one number that can undo Q3", layout: "big_number",
    nodes: [
      { type: "text", role: "eyebrow", value: "Retention" },
      { type: "stat", value: "4.1%", caption: "monthly logo churn, up from 2.6%" },
      { type: "chart", kind: "line", categories: ["Apr", "May", "Jun", "Jul", "Aug", "Sep"], series: [{ name: "Monthly logo churn", values: [2.6, 2.7, 2.9, 3.3, 3.8, 4.1] }], unit: "%" },
    ],
    notes: "Pause after the headline. Everything on the last six slides was good news, and this is the number that decides whether it lasts. Monthly churn went from 2.6% to 4.2% in two quarters. Say it once, then move straight to who is leaving.",
  },
  {
    section: "The risk", headline: "Small accounts leave in month four", layout: "chart",
    nodes: [{ type: "chart", kind: "line", categories: ["M1", "M2", "M3", "M4", "M5", "M6", "M7"], series: [{ name: "Small accounts", values: [100, 97, 93, 74, 71, 69, 68] }, { name: "Enterprise", values: [100, 99, 98, 97, 96, 95, 94] }], unit: "%" }],
    notes: "Retention by account size. Enterprise barely moves. Small accounts fall off a cliff in month four, when the first renewal invoice arrives.",
  },
  {
    section: "The risk", headline: "Customers who left say they never finished setup", layout: "bullets",
    nodes: [{ type: "bullets", items: [
      "Seven in ten leavers never connected their data",
      "Most never invited a second teammate",
      "Setup took longer than the trial for small teams",
      "Nobody from our side called before the renewal",
      "Help articles assumed an admin they did not have",
      "The first report arrived after they had decided",
      "Price was named by fewer than one in ten",
    ] }],
    notes: "From 38 exit interviews. The pattern is setup, not price.",
  },
  {
    section: "The ask", headline: "Three bets for Q4", layout: "three_column",
    nodes: [{ type: "items", style: "columns", items: [
      { label: "Bet one", title: "Guided setup for everyone", body: "Roll the pilot out to every new small account." },
      { label: "Bet two", title: "A call before month four", body: "Two success managers for accounts under 20 seats." },
      { label: "Bet three", title: "A report in week one", body: "Show value before the first invoice." },
    ] }],
    notes: "Three bets, in the order we would fund them.",
  },
  {
    section: "The ask", headline: "We need $1.2M for retention", layout: "big_number",
    nodes: [
      { type: "stat", value: "$1.2M", caption: "retention budget for Q4" },
      { type: "table", columns: ["Bet", "Cost", "Churn saved"], rows: [["Guided setup", "$520k", "0.6 pts"], ["Success managers", "$430k", "0.4 pts"], ["Week-one report", "$250k", "0.2 pts"]] },
    ],
    notes: "The ask is $1.2M. It pays back in two quarters if churn returns to under 3%.",
  },
  {
    section: "The ask", headline: "Approve today and churn is back under 3% by February", layout: "next_steps",
    nodes: [{ type: "items", style: "steps", items: [
      { title: "Approve the budget", body: "Today" },
      { title: "Guided setup for all", body: "Live by 15 November" },
      { title: "Success team hired", body: "By 1 December" },
      { title: "Churn under 3%", body: "February board meeting" },
    ] }],
    notes: "",
  },
];

export function q3Deck(): Deck {
  return {
    id: "q3-board-review",
    title: "Q3 Board Review",
    status: "ready",
    brief: {
      prompt: "Our Q3 board review. Revenue is up 34%, but monthly logo churn went from 2.6% to 4.1%. I need the board to approve a retention budget. Be honest about the churn before making the ask.",
      audience: "Board of directors", tone: "Direct, no spin", minutes: 20, deck_type: "board_update",
    },
    theme: THEME,
    slides: slides("q3", Q3),
    created_at: iso(60 * 26),
    updated_at: iso(42),
  };
}

export function q3Findings(): Finding[] {
  const f = (n: number, slide: number, rule: string, severity: Finding["severity"], title: string, detail: string, status: Finding["status"] = "open"): Finding => ({
    id: `q3-f${n}`, slide_id: `q3-s${slide}`, slide_index: slide, rule, severity, title, detail, status,
  });
  return [
    f(1, 2, "headline_not_claim", "low", "Slide 2 is a plain list with no claim in the headline", "You said the agenda should stay a plain list.", "kept"),
    f(2, 3, "min_font", "high", "The source line on slide 3 is too small to read from the back of a room", "It is 10 pt. Anything under 12 pt gets lost."),
    f(3, 7, "number_mismatch", "high", "Slide 7 quotes 4.2% but the slide says 4.1%", "The speaker notes say 4.2%. The number on the slide and in the chart is 4.1%."),
    f(4, 9, "too_many_bullets", "medium", "Slide 9 has seven bullets", "A room reads about four. I would keep the strongest four."),
    f(5, 11, "empty_slot", "medium", "The $1.2M on slide 11 does not say where it comes from", "A board will ask. One source line under the number is enough."),
    f(6, 12, "missing_notes", "low", "Slide 12 has no speaker notes", "The closing slide is where the ask lands. A sentence to say out loud helps."),
  ];
}

export function q3Messages(): Message[] {
  return [
    { id: "q3-m1", role: "user", scope: "deck", slide_id: null, text: "Write every headline as a claim, not a topic", status: "done", result: "Rewrote 9 headlines. 3 were already claims, so I left them alone.", version_ids: [], changed_slide_ids: [], created_at: iso(55) },
    { id: "q3-m2", role: "user", scope: "slide", slide_id: "q3-s7", text: "Make the 4.1% much bigger and put it on the accent colour", status: "done", result: "Done. The number now sits on a colour block, and the chart moved under the headline to make room.", version_ids: [], changed_slide_ids: ["q3-s7"], created_at: iso(44) },
  ];
}

export function rules(): Rule[] {
  return [
    { id: "r1", text: "Never use the word synergy", created_at: iso(60 * 24 * 30), source: null },
    { id: "r2", text: "Always show currency in USD", created_at: iso(60 * 24 * 30), source: null },
    { id: "r3", text: "The agenda slide stays a plain list", created_at: iso(50), source: "Kept a finding on Q3 Board Review" },
  ];
}

/** Outline for a brand-new mock deck. The real Strategist writes this from the prompt. */
export function genericOutline(prompt: string, count: number): { title: string; rows: { section: string; headline: string; layout: LayoutId }[] } {
  const words = prompt.replace(/[^\p{L}\p{N}\s%$.-]/gu, " ").trim().split(/\s+/);
  const topic = words.slice(0, 6).join(" ") || "Untitled deck";
  const title = topic.charAt(0).toUpperCase() + topic.slice(1).replace(/[.,]$/, "");
  const pool: { section: string; headline: string; layout: LayoutId }[] = [
    { section: "Opening", headline: title, layout: "title" },
    { section: "Opening", headline: "Here is what we will decide today", layout: "agenda" },
    { section: "Where we are", headline: "The situation changed faster than we planned for", layout: "bullets" },
    { section: "Where we are", headline: "One number shows the size of it", layout: "big_number" },
    { section: "Where we are", headline: "The trend has held for four quarters", layout: "chart" },
    { section: "The problem", headline: "Two things are holding us back", layout: "two_column" },
    { section: "The problem", headline: "People closest to it say the same thing", layout: "quote" },
    { section: "The plan", headline: "Three moves fix most of it", layout: "three_column" },
    { section: "The plan", headline: "The work fits in one quarter", layout: "timeline" },
    { section: "The plan", headline: "The options compare like this", layout: "table" },
    { section: "The ask", headline: "We need a decision this week", layout: "next_steps" },
    { section: "The ask", headline: "Say yes and we start on Monday", layout: "closing" },
  ];
  const n = Math.max(3, Math.min(count, 20));
  const rows = n >= pool.length ? [...pool] : [...pool.slice(0, n - 1), pool[pool.length - 1]];
  while (rows.length < n) rows.splice(rows.length - 1, 0, { section: "Appendix", headline: `Supporting detail ${rows.length - pool.length + 1} backs the plan`, layout: "appendix" });
  return { title, rows };
}

/** Content for a slide the mock "Writer" fills in. */
export function genericNodes(layout: LayoutId, headline: string): { nodes: Node[]; notes: string } {
  const h = head(headline);
  const notes = `Say the headline first: ${headline}. Then give the one piece of evidence on the slide and move on.`;
  const bullets: Node = { type: "bullets", items: ["The first point, in plain words", "The evidence that supports it", "What it means for the people in the room", "What happens next"] };
  const chart = (kind: "bar" | "line"): Node => ({ type: "chart", kind, categories: ["Q1", "Q2", "Q3", "Q4"], series: [{ name: "This year", values: [12, 18, 26, 31] }, { name: "Last year", values: [10, 12, 15, 17] }] });
  const cols = (style: "columns" | "steps" | "timeline"): Node => ({ type: "items", style, items: [
    { label: "First", title: "Start small", body: "Prove it with one team." },
    { label: "Then", title: "Widen it", body: "Roll out to the next three." },
    { label: "Finally", title: "Make it standard", body: "Write it into how we work." },
  ] });
  switch (layout) {
    case "title": case "section": case "closing":
      return { nodes: [h, { type: "text", role: "subhead", value: "A deck made with the Lectern mock API" }], notes };
    case "big_number": case "big_idea":
      return { nodes: [h, { type: "stat", value: "31%", caption: "the change that matters most" }, { type: "chart", kind: "line", categories: ["Q1", "Q2", "Q3", "Q4"], series: [{ name: "Trend", values: [12, 18, 26, 31] }], unit: "%" }], notes };
    case "chart": return { nodes: [h, chart("bar")], notes };
    case "dashboard":
      return { nodes: [h, { type: "stat", value: "31%", caption: "growth" }, { type: "stat", value: "4.2", caption: "average rating" }, { type: "stat", value: "12k", caption: "active users" }, chart("line")], notes };
    case "table": case "appendix":
      return { nodes: [h, { type: "table", columns: ["Option", "Cost", "Time", "Risk"], rows: [["Do nothing", "$0", "None", "High"], ["Fix the basics", "$120k", "6 weeks", "Low"], ["Rebuild", "$900k", "9 months", "Medium"]] }], notes };
    case "quote": return { nodes: [h, { type: "quote", text: "We lose a day every week working around it.", attribution: "Team lead, operations" }], notes };
    case "two_column": case "case_study":
      return { nodes: [h, bullets, { type: "image", alt: "A picture goes here", prompt: headline }], notes };
    case "three_column": case "team": case "diagram": return { nodes: [h, cols("columns")], notes };
    case "process": case "next_steps": return { nodes: [h, cols("steps")], notes };
    case "timeline": return { nodes: [h, cols("timeline")], notes };
    default: return { nodes: [h, bullets], notes };
  }
}

export const LAYOUTS: LayoutInfo[] = ([
  ["title", "Title", "Opens the deck with its name and one line of context"],
  ["agenda", "Agenda", "Lists what the talk will cover or decide"],
  ["section", "Section", "Marks the start of a new part"],
  ["big_idea", "Big idea", "One sentence the audience should remember"],
  ["bullets", "List", "A short list of points, five at most"],
  ["two_column", "Two column", "Text beside a picture, chart or second list"],
  ["three_column", "Three column", "Three parallel ideas side by side"],
  ["process", "Process", "Steps in order"],
  ["timeline", "Timeline", "Events along a line of time"],
  ["chart", "Chart", "One chart that proves the headline"],
  ["dashboard", "Dashboard", "A few key numbers with one chart"],
  ["table", "Table", "A small comparison table"],
  ["quote", "Quote", "Someone else's words, large"],
  ["case_study", "Case study", "A customer story: problem, what we did, result"],
  ["diagram", "Diagram", "How parts relate to each other"],
  ["team", "Team", "The people involved"],
  ["summary", "Summary", "The points to take away"],
  ["next_steps", "Next steps", "Who does what next"],
  ["closing", "Closing", "The last word and the ask"],
  ["appendix", "Appendix", "Backup detail for questions"],
  ["big_number", "Big number", "One number, very large, with its meaning"],
] as [LayoutId, string, string][]).map(([id, name, purpose]) => ({ id, name, purpose, slots: [] }));

export function connections(): Connection[] {
  return [
    { id: "offline", label: "Offline model", kind: "offline", base_url: null, has_key: false, status: "connected" },
    { id: "anthropic", label: "Anthropic", kind: "anthropic", base_url: null, has_key: false, status: "not_connected" },
    { id: "openai", label: "OpenAI", kind: "openai_compatible", base_url: "https://api.openai.com/v1", has_key: false, status: "not_connected" },
    { id: "openrouter", label: "OpenRouter", kind: "openai_compatible", base_url: "https://openrouter.ai/api/v1", has_key: false, status: "not_connected" },
    { id: "ollama", label: "Ollama", kind: "openai_compatible", base_url: "http://localhost:11434/v1", has_key: false, status: "not_connected" },
    { id: "gemini", label: "Gemini", kind: "gemini", base_url: null, has_key: false, status: "not_connected" },
  ];
}

export const MODELS: Record<string, string[]> = {
  offline: ["offline-1"],
  anthropic: ["claude-sonnet-5-5", "claude-haiku-5-5"],
  openai: ["gpt-large", "gpt-small"],
  openrouter: ["anthropic/claude-sonnet-5-5", "google/gemini-flash"],
  ollama: ["llama3"],
  gemini: ["gemini-pro", "gemini-flash"],
};

export function routing(): Routing {
  const r = { provider: "offline", model: "offline-1" };
  return { preset: "balanced", roles: { strategist: { ...r }, writer: { ...r }, art_director: { ...r }, renderer: { ...r }, critic: { ...r }, editor: { ...r } } };
}
