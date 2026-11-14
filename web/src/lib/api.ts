import type {
  BrandKit, BrandKitPatch, BrandMatch, ExportFormat,
  AskBody, Connection, ConnectionTest, ConnectionUpdate, CreateDeckBody, CriticReport, Deck, DeckPatch, DeckSummary,
  ExportResult, FindingAction, InterviewState, ShareLink, ShareProbe, ShareSettings, SharedDeck, MediaAsset, MediaGenerateBody, MediaJob, MediaKind, MediaProvider, MediaSuggestion, Slide, ChartSuggestion, DataInsertBody, DataSource, SlideData, SourcePreview, Health, LayoutInfo, Message, OutlineBody, RenderedSlide, Routing, Rule, Run, SlidePatch,
} from "./types";

/** JSON calls go through the Next.js rewrite (/api/* -> the API). */
const BASE = "/api";

export const IS_MOCK = process.env.NEXT_PUBLIC_LECTERN_MOCK === "1";

/** Server-Sent Events connect to the API directly, because proxies buffer streams. */
export const API_URL = IS_MOCK ? "" : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  /** True when the API could not be reached at all (as opposed to answering with an error). */
  unreachable: boolean;
  constructor(message: string, status: number, unreachable = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.unreachable = unreachable;
  }
}

const UNREACHABLE = "Lectern can't reach its server. Check that it is running, then try again.";

/** Calls that the shell needs at page load give up after this long, so a down API shows the banner fast. */
const FAST_TIMEOUT_MS = 4_000;

async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  let res: Response;
  const ctrl = timeoutMs ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: ctrl ? ctrl.signal : init?.signal,
      // FormData sets its own multipart Content-Type (with the boundary); forcing JSON breaks uploads.
      headers: init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    });
  } catch {
    if (timer) clearTimeout(timer);
    throw new ApiError(UNREACHABLE, 0, true);
  }
  let text: string;
  try {
    text = await res.text();
  } catch {
    throw new ApiError(UNREACHABLE, 0, true);
  } finally {
    if (timer) clearTimeout(timer);
  }
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    // The dev proxy answers 500/502/504 with a non-JSON body when nothing listens on the API port.
    if (res.status >= 500 && typeof detail !== "string") throw new ApiError(UNREACHABLE, res.status, true);
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Some of what was sent was not accepted. Check the fields and try again."
          : `Something went wrong (error ${res.status}).`;
    throw new ApiError(message, res.status);
  }
  return data as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/health", undefined, FAST_TIMEOUT_MS),

  listDecks: () => request<DeckSummary[]>("/decks", undefined, FAST_TIMEOUT_MS),
  createDeck: (body: CreateDeckBody) => request<Deck>("/decks", json("POST", body)),
  getDeck: (id: string) => request<Deck>(`/decks/${id}`),
  patchDeck: (id: string, body: DeckPatch) => request<Deck>(`/decks/${id}`, json("PATCH", body)),
  deleteDeck: (id: string) => request<unknown>(`/decks/${id}`, json("DELETE")),

  putOutline: (id: string, body: OutlineBody) => request<unknown>(`/decks/${id}/outline`, json("PUT", body)),
  regenerateOutline: (id: string, instruction?: string) =>
    request<unknown>(`/decks/${id}/outline/regenerate`, json("POST", instruction ? { instruction } : {})),
  approve: (id: string) => request<unknown>(`/decks/${id}/approve`, json("POST")),
  pause: (id: string) => request<unknown>(`/decks/${id}/pause`, json("POST")),
  resume: (id: string) => request<unknown>(`/decks/${id}/resume`, json("POST")),

  /** Additive endpoint; callers must cope with it being absent. */
  getRuns: (id: string) => request<Run[]>(`/decks/${id}/runs`),
  getRender: (id: string) => request<RenderedSlide[]>(`/decks/${id}/render`),
  getSlideRender: (id: string, sid: string) => request<RenderedSlide>(`/decks/${id}/slides/${sid}/render`),
  patchSlide: (id: string, sid: string, patch: SlidePatch) =>
    request<unknown>(`/decks/${id}/slides/${sid}`, json("PATCH", patch)),
  undoSlide: (id: string, sid: string) => request<unknown>(`/decks/${id}/slides/${sid}/undo`, json("POST")),
  /** Undo one Ask: exactly the slide versions it created; later edits to the same fields are kept. */
  undoMessage: (id: string, mid: string) =>
    request<{ reverted_slide_ids: string[]; kept: { slide_id: string; field: string; reason: string }[] }>(`/decks/${id}/messages/${mid}/undo`, json("POST")),

  ask: (id: string, body: AskBody) => request<{ message_id: string }>(`/decks/${id}/ask`, json("POST", body)),
  getMessages: (id: string) => request<Message[]>(`/decks/${id}/messages`),

  getCritic: (id: string) => request<CriticReport>(`/decks/${id}/critic`),
  actOnFinding: (id: string, fid: string, action: FindingAction) =>
    request<unknown>(`/decks/${id}/critic/findings/${fid}`, json("POST", { action })),
  fixAll: (id: string) => request<unknown>(`/decks/${id}/critic/fix-all`, json("POST")),

  listRules: () => request<Rule[]>("/rules"),
  addRule: (text: string) => request<Rule>("/rules", json("POST", { text })),
  deleteRule: (ruleId: string) => request<unknown>(`/rules/${ruleId}`, json("DELETE")),

  exportDeck: (id: string, includeNotes: boolean, format: ExportFormat = "pptx") =>
    request<ExportResult>(`/decks/${id}/export`, json("POST", { format, include_notes: includeNotes })),
  fileUrl: (fileId: string) => `${BASE}/files/${fileId}`,

  listLayouts: () => request<LayoutInfo[]>("/layouts"),

  getConnections: () => request<Connection[]>("/settings/connections"),
  putConnection: (body: ConnectionUpdate) => request<unknown>("/settings/connections", json("PUT", body)),
  testConnection: (connectionId: string) =>
    request<ConnectionTest>(`/settings/connections/${connectionId}/test`, json("POST")),
  getRouting: () => request<Routing>("/settings/routing"),
  putRouting: (body: Partial<Routing>) => request<unknown>("/settings/routing", json("PUT", body)),

  listMediaProviders: () => request<MediaProvider[]>("/media/providers"),
  suggestMedia: (id: string, sid?: string) =>
    request<MediaSuggestion>(`/decks/${id}/media/suggest${sid ? `?slide_id=${encodeURIComponent(sid)}` : ""}`),
  generateMedia: (id: string, body: MediaGenerateBody) => request<MediaJob>(`/decks/${id}/media/generate`, json("POST", body)),
  listMediaJobs: (id: string) => request<MediaJob[]>(`/decks/${id}/media/jobs`),
  listMedia: (id: string, opts: { slideId?: string; kind?: MediaKind } = {}) => {
    const q = new URLSearchParams();
    if (opts.slideId) q.set("slide_id", opts.slideId);
    if (opts.kind) q.set("kind", opts.kind);
    const qs = q.toString();
    return request<MediaAsset[]>(`/decks/${id}/media${qs ? `?${qs}` : ""}`);
  },
  uploadMedia: (id: string, file: File, sid?: string) => {
    const q = new URLSearchParams({ filename: file.name });
    if (sid) q.set("slide_id", sid);
    return request<MediaAsset>(`/decks/${id}/media/upload?${q}`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
    });
  },
  listSources: (deckId?: string) => request<DataSource[]>(`/sources${deckId ? `?deck_id=${encodeURIComponent(deckId)}` : ""}`),
  uploadSource: (file: File, deckId?: string) => {
    const q = new URLSearchParams({ filename: file.name });
    if (deckId) q.set("deck_id", deckId);
    return request<DataSource>(`/sources/upload?${q}`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
    });
  },
  addSourceLink: (url: string, deckId?: string) => request<DataSource>("/sources/link", json("POST", { url, deck_id: deckId })),
  deleteSource: (sourceId: string) => request<unknown>(`/sources/${sourceId}`, json("DELETE")),
  reloadSource: (sourceId: string) => request<DataSource>(`/sources/${sourceId}/reload`, json("POST")),
  attachSources: (id: string, sourceIds: string[]) => request<DataSource[]>(`/decks/${id}/sources`, json("POST", { source_ids: sourceIds })),
  previewSource: (sourceId: string, sheet?: string) =>
    request<SourcePreview>(`/sources/${sourceId}/preview${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`),
  suggestChart: (sourceId: string, sheet: string | undefined, range: string) =>
    request<ChartSuggestion>(`/sources/${sourceId}/suggest`, json("POST", { sheet, range })),
  sourceFileUrl: (sourceId: string) => `${BASE}/sources/${sourceId}/file`,
  getSlideData: (id: string, sid: string) => request<SlideData>(`/decks/${id}/slides/${sid}/data`),
  insertData: (id: string, sid: string, body: DataInsertBody) => request<Slide>(`/decks/${id}/slides/${sid}/data/insert`, json("POST", body)),
  refreshData: (id: string, sid: string) =>
    request<{ slide: Slide; changed: string[]; text_updates?: Record<string, string>; flagged?: string[] }>(`/decks/${id}/slides/${sid}/data/refresh`, json("POST")),
  fixDataNumbers: (id: string, sid: string) =>
    request<{ slide: Slide; fixed: number }>(`/decks/${id}/slides/${sid}/data/fix-numbers`, json("POST")),
  placeMedia: (id: string, sid: string, assetId: string) =>
    request<Slide>(`/decks/${id}/slides/${sid}/media`, json("POST", { asset_id: assetId })),
  /** Asset URLs come back as "/api/..."; they go through the same rewrite as JSON calls. */
  mediaUrl: (url: string) => (/^(https?:|data:|blob:)/.test(url) ? url : url.startsWith("/api/") ? url : `${BASE}${url.startsWith("/") ? "" : "/"}${url}`),

  getInterview: (id: string) => request<InterviewState>(`/decks/${id}/interview`),
  answerInterview: (id: string, questionId: string, answer: string) =>
    request<InterviewState>(`/decks/${id}/interview/answer`, json("POST", { question_id: questionId, answer })),
  skipInterview: (id: string, opts: { questionId?: string; all?: boolean } = {}) =>
    request<InterviewState>(`/decks/${id}/interview/skip`, json("POST", { question_id: opts.questionId, all: Boolean(opts.all) })),

  listShares: (id: string) => request<ShareLink[]>(`/decks/${id}/shares`),
  createShare: (id: string, body: ShareSettings = {}) => request<ShareLink>(`/decks/${id}/shares`, json("POST", body)),
  updateShare: (id: string, shareId: string, body: ShareSettings) =>
    request<ShareLink>(`/decks/${id}/shares/${shareId}`, json("PATCH", body)),
  deleteShare: (id: string, shareId: string) => request<unknown>(`/decks/${id}/shares/${shareId}`, json("DELETE")),
  probeShare: (token: string) => request<ShareProbe>(`/public/shares/${token}`),
  openShare: (token: string, body: { password?: string; visitor?: string }) =>
    request<SharedDeck>(`/public/shares/${token}/open`, json("POST", body)),
  pingShare: (token: string, viewId: string, slideId: string, seconds: number) =>
    request<unknown>(`/public/shares/${token}/views/${viewId}/ping`, json("POST", { slide_id: slideId, seconds })),
  shareDownloadUrl: (token: string, viewId: string) => `${BASE}/public/shares/${token}/download?view_id=${encodeURIComponent(viewId)}`,

  getMcpSetup: () => request<McpSetup>("/mcp/setup"),

  // Brand kits (U09)
  listBrandKits: () => request<BrandKit[]>("/brand-kits"),
  getBrandKit: (kitId: string) => request<BrandKit>(`/brand-kits/${kitId}`),
  createBrandKit: (form: FormData) => request<BrandKit>("/brand-kits", { method: "POST", body: form }),
  patchBrandKit: (kitId: string, body: BrandKitPatch) => request<BrandKit>(`/brand-kits/${kitId}`, json("PATCH", body)),
  deleteBrandKit: (kitId: string) => request<unknown>(`/brand-kits/${kitId}`, json("DELETE")),
  uploadBrandFile: (kitId: string, kind: "template" | "guide", file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<BrandKit>(`/brand-kits/${kitId}/${kind}`, { method: "POST", body: form });
  },
  addBrandRule: (kitId: string, text: string) => request<BrandKit>(`/brand-kits/${kitId}/rules`, json("POST", { text })),
  patchBrandRule: (kitId: string, ruleId: string, body: { text?: string; enabled?: boolean }) =>
    request<BrandKit>(`/brand-kits/${kitId}/rules/${ruleId}`, json("PATCH", body)),
  deleteBrandRule: (kitId: string, ruleId: string) => request<BrandKit>(`/brand-kits/${kitId}/rules/${ruleId}`, json("DELETE")),
  setDeckBrandKit: (id: string, brandKitId: string | null) =>
    request<unknown>(`/decks/${id}/brand-kit`, json("PUT", { brand_kit_id: brandKitId })),
  brandMatch: (id: string) => request<BrandMatch>(`/decks/${id}/brand-match`),

  eventsUrl: (id: string) => `${API_URL}/api/decks/${id}/events`,
};

/** Query keys in one place so the events hook and the screens agree. */
export const keys = {
  health: ["health"] as const,
  decks: ["decks"] as const,
  deck: (id: string) => ["deck", id] as const,
  render: (id: string) => ["render", id] as const,
  messages: (id: string) => ["messages", id] as const,
  critic: (id: string) => ["critic", id] as const,
  activity: (id: string) => ["activity", id] as const,
  rules: ["rules"] as const,
  mcpSetup: ["mcp-setup"] as const,
  layouts: ["layouts"] as const,
  connections: ["connections"] as const,
  routing: ["routing"] as const,
  mediaProviders: ["media-providers"] as const,
  media: (id: string) => ["media", id] as const,
  mediaJobs: (id: string) => ["media-jobs", id] as const,
  mediaSuggest: (id: string, sid: string) => ["media-suggest", id, sid] as const,
  interview: (id: string) => ["interview", id] as const,
  shares: (id: string) => ["shares", id] as const,
  brandKits: ["brand-kits"] as const,
  sources: (deckId?: string) => ["sources", deckId ?? "all"] as const,
  sourcePreview: (sourceId: string, sheet?: string) => ["source-preview", sourceId, sheet ?? ""] as const,
  slideData: (id: string, sid: string) => ["slide-data", id, sid] as const,
  brandKit: (kitId: string) => ["brand-kit", kitId] as const,
  brandMatch: (id: string) => ["brand-match", id] as const,
};

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Try again.";
}

/** GET /mcp/setup: how to connect each agent client to Lectern's MCP server. */
export type McpClientSetup = {
  id: string; name: string; where: string; format: "shell" | "json" | "toml"; file: string | null;
  stdio: string; http: string | null;
};
export type McpSetup = {
  name: string;
  stdio: { command: string; args: string[]; note: string };
  http: { url: string; note: string };
  clients: McpClientSetup[];
};
