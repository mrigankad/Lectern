# Lectern build spec (v0.1)

Lectern is an AI presentation tool. The user says what they need to say, AI agents plan,
write, lay out and check the deck, and it exports as an editable PowerPoint file.
The design lives in the Paper file "Lectern · Brand & Product" (pages: brand, Product plan, UX flows U00–U16).
This document is the contract between the backend (`server/`) and the web app (`web/`).

## 1. Scope of this first build

A working local product, end to end, with no account system:

1. Create a deck from a prompt (U03) → 2. Strategist drafts an outline → 3. user edits and approves it (U05)
→ 4. agents build the slides while the UI shows live progress (U06) → 5. workspace: view slides, edit text,
ask for changes in chat (U07) → 6. Critic report with fix / keep (U08) → 7. export an editable `.pptx` with an
editability report (U13). Plus Home (U02) and Connections and model routing (U12).

Out of scope for now (later phases): brand-kit import from .potx (U09), spreadsheet-linked charts (U10),
media generation (U11), share links (U14), present mode (U15), MCP server (U16), accounts, billing, PDF and
Google Slides export, vision-based critique. Leave clean seams for them; do not stub UI that pretends they work.

## 2. Repository layout

```
docs/SPEC.md            this file
references/*.md         existing knowledge: layout patterns, deck types, visual guidelines (reuse as agent knowledge)
server/                 Python 3.13, FastAPI, SQLModel, SQLite (uv project, package name `lectern`)
  lectern/
    main.py             app factory, mounts routers under /api, CORS for http://localhost:3000
    db.py, models.py    SQLite at ./data/lectern.db (WAL). Tables: deck, slide, slide_version, run, message, finding, rule, connection, role_route
    schema.py           Pydantic models for the scene graph and API payloads (section 3, 5)
    layouts/            layout registry: one typed layout per pattern in references/layout-patterns.md
    engine/place.py     deterministic layout: Slide + Theme -> RenderedSlide (absolute boxes on a 1920x1080 canvas)
    engine/lint.py      deterministic checks (section 6)
    export/pptx.py      RenderedSlide -> .pptx with native text boxes, tables and charts (python-pptx)
    export/report.py    editability report: counts of native objects vs pictures
    llm/                provider router (section 7) incl. an offline provider
    agents/             strategist, writer, art_director, renderer, critic, editor + pipeline.py
    events.py           in-process pub/sub -> SSE
    routers/            decks, slides, ask, critic, export, settings, layouts
  tests/                pytest; must pass with the offline provider and no network
web/                    Next.js 15 (App Router), React 19, TypeScript, Tailwind 4, TanStack Query (pnpm)
```

API on `http://localhost:8000`, web on `http://localhost:3000`. The web app calls the API through a Next.js
rewrite of `/api/*` to `http://localhost:8000/api/*` (SSE uses the absolute API URL to avoid proxy buffering).

## 3. Scene graph (the single source of truth)

A slide is typed data. The web canvas, the lint checks and the PPTX exporter all read the same data.

```ts
type Deck = {
  id: string; title: string; status: "draft" | "outline_ready" | "building" | "ready" | "failed";
  brief: { prompt: string; audience?: string; goal?: string; minutes?: number; tone?: string; deck_type?: string };
  theme: Theme; slides: Slide[]; created_at: string; updated_at: string;
};
type Theme = {
  name: string; font: string;                       // default "Urbanist"
  colors: { bg: string; ink: string; body: string; muted: string; line: string; surface: string; accent: string; on_accent: string };
  chart_colors: string[];
};
type Slide = {
  id: string; index: number;                         // 1-based order
  section?: string;                                  // e.g. "The risk"
  headline: string;                                  // written as a claim
  layout: LayoutId;
  nodes: Node[];                                     // content, no coordinates
  notes: string;                                     // speaker notes
  status: "queued" | "writing" | "rendering" | "checking" | "sent_back" | "ready";
  score?: number;                                    // 0-100 from the Critic
};
type Node =
  | { type: "text"; role: "eyebrow" | "headline" | "subhead" | "body" | "caption"; value: string }
  | { type: "bullets"; items: string[] }
  | { type: "stat"; value: string; caption?: string; source?: string }
  | { type: "chart"; kind: "bar" | "line" | "area" | "pie"; title?: string; categories: string[];
      series: { name: string; values: number[] }[]; unit?: string; data_ref?: string }
  | { type: "table"; columns: string[]; rows: string[][] }
  | { type: "quote"; text: string; attribution?: string }
  | { type: "items"; style: "columns" | "steps" | "timeline"; items: { title: string; body?: string; label?: string }[] }
  | { type: "image"; src?: string; prompt?: string; alt: string };
type LayoutId =
  | "title" | "agenda" | "section" | "big_idea" | "bullets" | "two_column" | "three_column" | "process"
  | "timeline" | "chart" | "dashboard" | "table" | "quote" | "case_study" | "diagram" | "team"
  | "summary" | "next_steps" | "closing" | "appendix" | "big_number";
```

Every slide's headline is also present as a `text` node with role `headline` (the renderer guarantees this).

### Rendered form (output of `engine/place.py`)

```ts
type RenderedSlide = {
  id: string; index: number; width: 1920; height: 1080; background: string; elements: Element[];
};
type Element = {
  id: string; node: number | null;                   // index into slide.nodes, null for decoration
  kind: "text" | "rect" | "line" | "chart" | "table" | "image";
  x: number; y: number; w: number; h: number;        // px on the 1920x1080 canvas
  text?: string; bullets?: string[];
  style?: { font_size?: number; font_weight?: 400 | 700; color?: string; align?: "left" | "center" | "right";
            valign?: "top" | "middle" | "bottom"; line_height?: number; fill?: string; stroke?: string;
            stroke_width?: number; uppercase?: boolean; letter_spacing?: number };
  chart?: { kind: "bar" | "line" | "area" | "pie"; categories: string[]; series: { name: string; values: number[] }[];
            colors: string[]; unit?: string };
  table?: { columns: string[]; rows: string[][] };
  src?: string; alt?: string;
};
```

Font sizes are in canvas px (1920 wide); the exporter converts px to points at 13.333in × 7.5in (1px = 0.5pt).
The web canvas draws elements as absolutely positioned boxes inside a 1920×1080 stage scaled with CSS transform.

## 4. Pipeline

`POST /decks` → Strategist writes the outline (title, sections, per slide: headline, layout, one-line intent)
→ deck `outline_ready`. User edits (PUT outline) and approves → deck `building`. For each slide, in order with
limited concurrency (3): Writer fills nodes and notes → Art Director confirms or changes the layout →
Renderer validates nodes against the layout slots → Critic runs lint; on a failing rule the slide is
`sent_back` once to the Writer/Art Director with the findings, then re-checked → `ready`. When all slides are
ready the deck is `ready`. Each agent step is a `run` row (role, status, provider, model, tokens, started/ended).
Every content change writes a `slide_version`. The user's rules (table `rule`) are injected into every agent prompt.
Runs interrupted by a restart are marked failed on startup so the UI can offer Retry.

Agents return structured data through tool use / JSON schema, never regex-parsed prose.
Agent knowledge comes from `references/*.md` (layout choice, deck types, visual rules).

## 5. HTTP API (all under `/api`, JSON)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | `{ ok: true, provider: string }` |
| GET | `/decks` | list: id, title, status, slide_count, updated_at, progress `{ready,total}` |
| POST | `/decks` | body `{ prompt, audience?, goal?, minutes?, tone?, slide_count? }` → Deck (outline generation starts) |
| GET | `/decks/{id}` | full Deck |
| DELETE | `/decks/{id}` | delete |
| PUT | `/decks/{id}/outline` | body `{ title, slides: [{ id?, section?, headline, layout }] }` (reorder, add, remove, edit) |
| POST | `/decks/{id}/outline/regenerate` | body `{ instruction? }` e.g. "make it shorter" |
| POST | `/decks/{id}/approve` | start the build |
| POST | `/decks/{id}/pause`, `/resume` | pause or resume the build |
| GET | `/decks/{id}/render` | `RenderedSlide[]` |
| GET | `/decks/{id}/slides/{sid}/render` | one `RenderedSlide` |
| PATCH | `/decks/{id}/slides/{sid}` | body `{ headline?, layout?, nodes?, notes? }` manual edit, re-lints |
| POST | `/decks/{id}/ask` | body `{ scope: "slide" | "deck", slide_id?, message }` → `{ message_id }`; result arrives by events |
| GET | `/decks/{id}/messages` | chat history: role, scope, slide_id, text, result, version ids for undo |
| POST | `/decks/{id}/slides/{sid}/undo` | restore the previous slide_version |
| POST | `/decks/{id}/messages/{mid}/undo` | undo one Ask: revert exactly the versions it created (server/README.md, Undo) |
| GET | `/decks/{id}/critic` | `{ score, story, design, editability, findings: Finding[] }` |
| POST | `/decks/{id}/critic/findings/{fid}` | body `{ action: "fix" | "keep" | "reopen" }` ("keep" also creates a rule) |
| POST | `/decks/{id}/critic/fix-all` | fix every open finding |
| GET/POST/DELETE | `/rules` | the user's standing rules `{ id, text, created_at, source? }` |
| POST | `/decks/{id}/export` | body `{ format: "pptx", include_notes: boolean }` → `{ file_id, filename, bytes, report }` |
| GET | `/files/{file_id}` | download |
| GET | `/layouts` | layout registry: id, name, purpose, slots |
| GET/PUT | `/settings/connections` | providers: id, label, kind, base_url?, has_key, status; PUT sets key/base_url |
| POST | `/settings/connections/{id}/test` | `{ ok, detail, models? }` |
| GET/PUT | `/settings/routing` | `{ preset, roles: { strategist, writer, art_director, renderer, critic, editor: { provider, model } } }` |
| GET | `/decks/{id}/events` | Server-Sent Events (below) |

```ts
type Finding = { id: string; slide_id: string; slide_index: number; rule: string; severity: "high" | "medium" | "low";
  title: string; detail: string; status: "open" | "fixed" | "kept"; };
type ExportReport = { total_objects: number; editable_objects: number; pictures: number; charts: number; tables: number;
  text_boxes: number; notes_slides: number; checks: { label: string; detail: string; ok: boolean }[] };
```

Errors: HTTP status + `{ detail: string }` in plain language.

### Events (SSE, `event:` name + JSON `data:`)

`deck.updated {status, progress}` · `outline.ready {}` · `slide.updated {slide_id, index, status, score?}` ·
`run.updated {id, role, slide_index?, status, summary}` (summary is one plain sentence for the activity feed) ·
`message.updated {id, status, result}` · `finding.updated {id, status}` · `ping` every 20s.
The web app invalidates the matching query on each event (deck, render, critic, messages).

## 6. Lint rules (deterministic Critic)

`text_overflow` (estimated text size vs its box), `min_font` (body under 24px canvas = 12pt, labels under 20px),
`too_many_bullets` (> 5), `long_bullet` (> 16 words), `long_headline` (> 12 words), `headline_not_claim`
(no verb / topic-only title), `missing_notes`, `chart_too_many_series` (> 5), `chart_wrong_kind`
(pie with > 6 slices, line with < 3 points), `number_mismatch` (a number in notes or text that differs from the
slide's stat/chart value), `empty_slot` (required layout slot missing), `contrast` (text vs background < 4.5:1),
`rule_violation` (a user rule's banned word appears), `placeholder_text` (bracketed or TBD placeholder text left on the slide; the notes may say what to add). Scores: each slide starts at 100 and loses points by
severity; deck score is the mean. Sub-scores group rules: Story (headline/notes/claims), Design
(overflow/font/bullets/contrast), Editability (from the export report).

## 7. Model providers

A router maps each agent role to `{provider, model}`. Providers:
`anthropic` (Anthropic SDK, tool use), `openai_compatible` (OpenAI, OpenRouter, LiteLLM gateway, Groq, DeepSeek,
Mistral, Ollama: all through one client with a base URL), `gemini` (optional, may be routed through an
OpenAI-compatible endpoint), and `offline`: a deterministic provider with no network that produces a sensible
deck from the prompt (uses references/deck-types.md for structure). `offline` is the default when no key is
configured, so the product and the tests run out of the box. Keys are stored in the local database and are
never returned by the API (`has_key` only). Retries with exponential backoff on 429/5xx; prompt caching on the
shared system context where the provider supports it. Default Anthropic models: `claude-sonnet-5-5` for
strategist, writer, art director, editor; `claude-haiku-5-5` for renderer and critic.

## 8. Visual system for the web app

Lectern follows the owner's house product style (the "Wayam product UI"; reference Paper file
`01M7AHTJPHQJKNNFD4GEVNJAQZ`, page `p-C-0`, artboards `1QL-0`, `248-0`, `26Y-0`).

- Font: Urbanist only (400 body, 700 headings, labels, buttons). No monospace.
- Colours: bg #FFFFFF; surface #F7F7F8; surface-2 #EFEFF2; hairline #E8E8EC; line-strong #D9D9E0; ink #16181D;
  body #5E6370; muted #7A7F8C; action #2563EB (white text; primary buttons and the product tile use the gradient linear-gradient(180deg, #3B82F6 0%, #1D4ED8 100%)) and action-soft #EAF1FF; pass #16A06A / #E7F6EF;
  fail #E5484D / #FDECEC; warn #B87400 / #FFF4DC; ai #7C5CFF / #F1EDFF; teal #0E8F8E / #E3F5F4.
- Text on a saturated fill is always white. No chrome yellow, no square corners.
- Radii: 6px chips, 8px buttons and inputs, 12px cards, 999px pills. Cards: white, 1px hairline, no shadow.
- Shell: 240px left sidebar on the surface colour (product tile, search, nav with line icons, section labels,
  model-cost card, user row) and a 48px top bar (breadcrumb left; context chip, bell, primary button right).
- Status as soft-tint pills. Agent proposals in an AI-soft card; human decisions in a white card with the primary button.
- Line icons (lucide-react). Clay 3D icons for page headers and empty states where available.
- The default deck theme (slides) is neutral: white, ink text, Urbanist, accent #2563EB.

Take exact layout and spacing from the Paper UX-flow artboards with `get_jsx` / `get_computed_styles`.
