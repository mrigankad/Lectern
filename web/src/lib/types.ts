// Mirrors docs/SPEC.md section 3 (scene graph) and section 5 (HTTP API).
// Fields marked "assumed" are not spelled out in the spec; see web/README.md.

export type DeckStatus = "interview" | "draft" | "outline_ready" | "building" | "ready" | "failed";
export type SlideStatus = "queued" | "writing" | "rendering" | "checking" | "sent_back" | "ready";

export type LayoutId =
  | "title" | "agenda" | "section" | "big_idea" | "bullets" | "two_column" | "three_column" | "process"
  | "timeline" | "chart" | "dashboard" | "table" | "quote" | "case_study" | "diagram" | "team"
  | "summary" | "next_steps" | "closing" | "appendix" | "big_number";

export type ChartKind = "bar" | "line" | "area" | "pie";
export type Series = { name: string; values: number[] };

export type Node =
  | { type: "text"; role: "eyebrow" | "headline" | "subhead" | "body" | "caption"; value: string }
  | { type: "bullets"; items: string[] }
  | { type: "stat"; value: string; caption?: string; source?: string }
  | { type: "chart"; kind: ChartKind; title?: string; categories: string[]; series: Series[]; unit?: string; data_ref?: string }
  | { type: "table"; columns: string[]; rows: string[][] }
  | { type: "quote"; text: string; attribution?: string }
  | { type: "items"; style: "columns" | "steps" | "timeline"; items: { title: string; body?: string; label?: string }[] }
  | { type: "image"; src?: string; prompt?: string; alt: string; asset_id?: string };

export type Theme = {
  name: string;
  font: string;
  colors: { bg: string; ink: string; body: string; muted: string; line: string; surface: string; accent: string; on_accent: string };
  chart_colors: string[];
  brand_kit_id?: string | null; // additive: brand kit the theme came from
  logo?: string | null;
  logo_ratio?: number | null;
};

export type Slide = {
  id: string;
  index: number;
  section?: string | null;
  headline: string;
  layout: LayoutId;
  nodes: Node[];
  notes: string;
  status: SlideStatus;
  /** The build is paused and this slide's next step waits for Resume (status names the last step). */
  paused?: boolean;
  score?: number | null;
  /** Additive in the backend: the Strategist one-line intent for the slide. */
  intent?: string | null;
};

export type Brief = { prompt: string; audience?: string; goal?: string; minutes?: number; tone?: string; deck_type?: string };

export type Deck = {
  id: string;
  title: string;
  status: DeckStatus;
  brief: Brief;
  theme: Theme;
  slides: Slide[];
  created_at: string;
  updated_at: string;
  // Additive fields the backend sends beyond the spec; all optional here.
  paused?: boolean;
  progress?: Progress;
  error?: string | null;
  icon?: string | null;
  icon_color?: string | null;
};

export type Progress = { ready: number; total: number };

export type DeckSummary = {
  id: string;
  title: string;
  status: DeckStatus;
  slide_count: number;
  updated_at: string;
  progress: Progress;
  icon?: string | null;
  icon_color?: string | null;
};

export type DeckPatch = { title?: string; icon?: string | null; icon_color?: string | null };

// Rendered form (output of engine/place.py)
export type ElementStyle = {
  font_size?: number;
  font_weight?: 400 | 700;
  color?: string;
  align?: "left" | "center" | "right";
  valign?: "top" | "middle" | "bottom";
  line_height?: number;
  fill?: string;
  stroke?: string;
  stroke_width?: number;
  uppercase?: boolean;
  letter_spacing?: number;
  /** Additive: corner radius in canvas px. */
  radius?: number;
};

export type ChartSpec = { kind: ChartKind; categories: string[]; series: Series[]; colors: string[]; unit?: string };

export type SlideElement = {
  id: string;
  node: number | null;
  kind: "text" | "rect" | "line" | "chart" | "table" | "image";
  x: number;
  y: number;
  w: number;
  h: number;
  text?: string;
  bullets?: string[];
  style?: ElementStyle;
  chart?: ChartSpec;
  table?: { columns: string[]; rows: string[][] };
  src?: string;
  alt?: string;
};

export type RenderedSlide = {
  id: string;
  index: number;
  width: 1920;
  height: 1080;
  background: string;
  elements: SlideElement[];
};

// Requests
export type CreateDeckBody = { prompt: string; audience?: string; goal?: string; minutes?: number; tone?: string; slide_count?: number; interview?: boolean; source_ids?: string[] };
export type OutlineSlide = { id?: string; section?: string; headline: string; layout: LayoutId };
export type OutlineBody = { title: string; slides: OutlineSlide[] };
export type SlidePatch = { headline?: string; layout?: LayoutId; nodes?: Node[]; notes?: string };
export type AskBody = { scope: "slide" | "deck"; slide_id?: string; message: string };

// Chat. The spec lists "role, scope, slide_id, text, result, version ids for undo";
// status, changed_slide_ids and created_at follow server/lectern/schema.py and are optional here.
export type Message = {
  id: string;
  role: "user" | "assistant" | string;
  scope: "slide" | "deck";
  slide_id?: string | null;
  text: string;
  result?: string | { summary?: string; text?: string } | null;
  status?: "pending" | "running" | "done" | "failed" | string;
  version_ids?: string[];
  changed_slide_ids?: string[];
  /** The Ask was undone (POST /decks/{id}/messages/{mid}/undo). */
  undone?: boolean;
  created_at?: string;
};

export type Severity = "high" | "medium" | "low";
export type Finding = {
  id: string;
  slide_id: string;
  slide_index: number;
  rule: string;
  severity: Severity;
  title: string;
  detail: string;
  status: "open" | "fixed" | "kept";
};
export type CriticReport = { score: number; story: number; design: number; editability: number; findings: Finding[] };
export type FindingAction = "fix" | "keep" | "reopen";

export type Rule = { id: string; text: string; created_at: string; source?: string | null };

export type ExportReport = {
  total_objects: number;
  editable_objects: number;
  pictures: number;
  charts: number;
  tables: number;
  text_boxes: number;
  notes_slides: number;
  checks: { label: string; detail: string; ok: boolean }[];
};
export type ExportResult = { file_id: string; filename: string; bytes: number; report: ExportReport };

export type LayoutInfo = { id: LayoutId; name: string; purpose: string; slots?: unknown };

export type Connection = {
  id: string;
  label: string;
  kind: string; // "anthropic" | "openai_compatible" | "gemini" | "offline"
  base_url?: string | null;
  has_key: boolean;
  status: string; // assumed: "connected" | "not_connected" | "error" (anything else is shown as written)
  detail?: string | null;
};
export type ConnectionUpdate = { id: string; api_key?: string; base_url?: string };
export type ConnectionTest = { ok: boolean; detail: string; models?: string[] };

export type Role = "strategist" | "writer" | "art_director" | "renderer" | "critic" | "editor";
export type RoleRoute = { provider: string; model: string };
export type RoutingPreset = { id?: string; label?: string; name?: string; description?: string; [k: string]: unknown };
export type Routing = { preset: string; roles: Record<Role, RoleRoute>; presets?: RoutingPreset[] };

export type Health = { ok: boolean; provider: string };

// Events (SSE)
export type DeckUpdatedEvent = { status: DeckStatus; progress: Progress };
export type SlideUpdatedEvent = { slide_id: string; index: number; status: SlideStatus; paused?: boolean; score?: number };
export type RunEvent = { id: string; role: string; slide_index?: number | null; status: string; summary: string };
/** GET /decks/{id}/runs is additive in the backend (not in the spec): the feed history. */
export type Run = RunEvent & { started_at?: string; ended_at?: string | null };
export type MessageUpdatedEvent = { id: string; status: string; result?: unknown };
export type FindingUpdatedEvent = { id: string; status: Finding["status"] };

// Media (additive)
export type MediaKind = "image" | "video";
export type MediaProvider = { id: string; label: string; kinds: MediaKind[]; connected: boolean; is_default: boolean; detail?: string | null; cost_hint?: string | null };
export type MediaSuggestion = { prompt: string; style: string; slide_index?: number | null; headline?: string | null };
export type MediaGenerateBody = { slide_id?: string; prompt: string; kind: MediaKind; aspect: string; providers: string[]; style?: string; count?: number };
export type MediaJob = {
  id: string; deck_id: string; slide_id?: string | null; kind: MediaKind; prompt: string; aspect: string; providers: string[];
  status: "pending" | "running" | "done" | "failed"; asset_ids: string[]; errors: { provider: string; detail: string }[]; created_at: string;
};
export type MediaAsset = {
  id: string; deck_id: string; slide_id?: string | null; job_id?: string | null; provider: string; kind: MediaKind; prompt: string;
  aspect?: string | null; url: string; poster_url?: string | null; width: number; height: number; cost_estimate?: number | null; created_at: string;
};
export type MediaUpdatedEvent = { job_id: string; status: MediaJob["status"]; asset_ids: string[]; errors: MediaJob["errors"] };

// Strategist interview (U04): additive endpoints /decks/{id}/interview.
export type InterviewKey = "audience" | "goal" | "minutes";
export type InterviewQuestion = {
  id: string; key: InterviewKey; text: string; hint: string; chips: string[]; answer: string | null; skipped: boolean;
  /** Answered by the new-deck form; shown as answered with "Change", never asked. */
  from_brief?: boolean;
};
export type KeyNumber = { value: string; label: string; tone: "good" | "bad" | "neutral" };
export type InterviewState = {
  deck_id: string; status: "open" | "done"; questions: InterviewQuestion[]; current: string | null;
  understood: { audience?: string | null; goal?: string | null; minutes?: number | null; time?: string | null; numbers: KeyNumber[]; ask?: string | null };
};

// Share links (U14): additive endpoints /decks/{id}/shares and /public/shares/{token}.
export type ShareAccess = "anyone" | "password";
export type ShareSlideStat = { index: number; slide_id: string; headline: string; seconds: number; avg_seconds: number };
export type ShareStats = {
  opens: number; visitors: number; total_seconds: number; avg_seconds: number; slides: ShareSlideStat[]; most_viewed?: ShareSlideStat | null;
};
export type ShareLink = {
  id: string; deck_id: string; token: string; path: string; access: ShareAccess; has_password: boolean;
  allow_download: boolean; show_notes: boolean; expires_at: string | null; expired: boolean; created_at: string; stats: ShareStats;
};
export type ShareSettings = {
  access?: ShareAccess; password?: string; allow_download?: boolean; show_notes?: boolean; expires_in_days?: number | null;
};
export type ShareProbe = { title: string; requires_password: boolean; slide_count: number };
export type SharedDeck = {
  view_id: string; title: string; allow_download: boolean; show_notes: boolean;
  slides: { id: string; index: number; headline: string; notes?: string }[]; render: RenderedSlide[];
};

// ---------------------------------------------------------------- export formats and brand kits (U09)
export type ExportFormat = "pptx" | "pdf" | "images" | "notes";
export type BrandRuleKind = "colors" | "font" | "logo" | "min_size" | "note";
export type BrandRule = {
  id: string; text: string; kind: BrandRuleKind; params: Record<string, unknown>; enabled: boolean;
  source: "auto" | "guide" | "user";
};
export type BrandKit = {
  id: string; name: string;
  palette: { slot?: string; name: string; hex: string }[];
  fonts: { heading?: string; body?: string };
  logos: { id: string; file: string; width: number; height: number; primary?: boolean; url: string }[];
  layouts: { index: number; name: string; placeholders: string[] }[];
  rules: BrandRule[];
  theme: Theme;
  template_file?: string | null; guide_file?: string | null;
  created_at: string; updated_at: string;
  deck_count?: number;
  decks?: { id: string; title: string }[];
};
export type BrandKitPatch = { name?: string; fonts?: { heading?: string; body?: string }; primary_logo?: string };
export type BrandMatch = {
  brand_kit_id: string | null; brand_kit_name?: string; score: number | null;
  rules: { id: string; text: string; kind: BrandRuleKind; enabled: boolean; checkable: boolean; passed: boolean;
    failing: { slide_id: string; slide_index: number; detail: string }[] }[];
};

// Data sources (server/lectern/routers/sources.py)
export type SourceKind = "xlsx" | "csv" | "pdf" | "docx" | "text" | "url" | "gsheet";
export type DataSource = {
  id: string; deck_id: string | null; name: string; kind: SourceKind; url: string | null; bytes: number;
  status: "ready" | "failed"; error: string | null;
  summary: { sheets: { name: string; rows: number; cols: number }[]; chunks: number; pages: number | null; title: string | null };
  created_at: string; updated_at: string;
};
export type SourcePreview = {
  source: DataSource; sheets: string[]; sheet?: string; rows?: string[][]; chunks: { ref: string; text: string }[];
};
export type ChartAlternative = { kind: ChartKind | "table"; ok: boolean; reason: string };
export type ChartSuggestion = {
  ok: boolean; reason: string; kind?: ChartKind; alternatives?: ChartAlternative[]; categories?: string[];
  series?: Series[]; unit?: string | null; headline?: string; warnings?: string[];
  data_ref: string; cells_label: string; range: string; sheet: string;
};
export type DataMismatch = { rule: string; severity: "high" | "medium" | "low"; title: string; detail: string; key: string };
export type SlideData = {
  slide_id: string; index: number; linked: { node: number; type: string; data_ref: string }[]; mismatches: DataMismatch[];
};
export type DataInsertBody = { data_ref: string; as?: "chart" | "stat"; kind?: ChartKind | "table"; title?: string; headline?: string };
