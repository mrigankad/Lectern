# Lectern web app

The browser side of Lectern: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4, TanStack Query,
lucide-react. The contract with the backend is `../docs/SPEC.md`.

## Run it

Requirements: Node 20 or newer and pnpm.

```bash
cd web
pnpm install
```

### Against the real API

Start the API first (from the repository root):

```bash
cd server
uv run uvicorn lectern.main:app --port 8000
```

Then the web app:

```bash
cd web
pnpm dev            # http://localhost:3000
```

`/api/*` is rewritten to `http://localhost:8000/api/*`. The live event stream connects to the API directly
(proxies buffer streams). If the API runs somewhere else, copy `.env.example` to `.env.local` and set
`NEXT_PUBLIC_API_URL`; it is used for both.

If the API is not running, every screen shows a banner that says so and how to start it.

### Against the mock API (no backend needed)

```bash
cd web
pnpm dev:mock       # http://localhost:3000
```

This sets `LECTERN_MOCK=1`, which rewrites `/api/*` to a route inside the app (`/mock-api/*`) that imitates
the spec in memory. It starts with three decks: "Q3 Board Review" (finished, with Critic findings, chat
history and rules), "Team offsite agenda" (outline waiting for approval) and "Series A pitch · Northwind"
(building, finishes in about half a minute). New decks get a generic outline and generic slides; timers stand
in for the agents. Everything resets when the dev server restarts. The mock export downloads a small text
file, not a .pptx.

The mock lives in `src/mock/` and `src/app/mock-api/`. Nothing else imports it, and the route answers 404
unless `LECTERN_MOCK=1`.

### Checks

```bash
pnpm lint
pnpm typecheck
pnpm build
```

## Where things are

| Path | What |
|---|---|
| `src/app/globals.css` | Design tokens (spec section 8): colours, radii, the primary-button gradient. Change the look here. |
| `src/components/Shell.tsx` | The shell: 240px sidebar, 48px top bar, the "API unreachable" banner, the step chip. |
| `src/components/ui.tsx` | Buttons, pills, cards, AI card, page header, loading / error / empty states, toggle, select chip. |
| `src/components/SlideCanvas.tsx`, `ChartSvg.tsx` | Draws a `RenderedSlide` on a 1920×1080 stage scaled with a CSS transform; charts in inline SVG. |
| `src/lib/types.ts` | Types mirroring spec sections 3 and 5. |
| `src/lib/api.ts` | The typed API client and the query keys. |
| `src/lib/events.ts` | `useDeckEvents`: subscribes to `/api/decks/{id}/events` and invalidates the matching queries. |
| `src/lib/hooks.ts` | Deck queries and the status gate that sends a deck to the right screen. |
| `src/lib/edit.ts` | Maps a clicked text box on the slide back to the node field it shows, for in-place editing. |

## Routes

| Route | Screen |
|---|---|
| `/` | Home: start-from shortcuts, decks with live status. `?q=` searches, `?show=needs-you` filters. |
| `/new` | New deck composer. `?start=notes|report|pitch|update|numbers` prefills the prompt. |
| `/decks/[id]/outline` | Outline review (deck status `draft`, `outline_ready`). |
| `/decks/[id]/build` | Live build (`building`, `failed`). |
| `/decks/[id]` | Workspace (`ready`; `?view=slides` opens it while still building). |
| `/decks/[id]/review` | Critic report. |
| `/decks/[id]/export` | Export. |
| `/connections` | Model connections and routing. |
| `/rules` | The standing rules. |

Opening a deck on a screen that does not fit its status redirects to the one that does.

## What the app assumes beyond the spec

These were checked against `server/lectern/schema.py` and the routers where they existed; all are read
defensively.

- `Deck` may carry `paused`, `progress` and `error`; `Slide` may carry `intent`; element styles may carry `radius`.
- `Message` has `status` (`pending` / `done` / `failed`) and `changed_slide_ids`. "Undo" on a chat result calls
  `POST /slides/{sid}/undo` for each of those slides (or the message's `slide_id`).
- `DELETE /rules/{id}` deletes one rule. `POST /rules` takes `{ text }`.
- `PUT /settings/connections` takes `{ id, api_key?, base_url? }`.
- `PUT /settings/routing` with only `{ preset }` applies that preset on the server; with `{ preset: "custom", roles }`
  it sets models by hand. `GET` may include `presets: [{ id, label, description }]`.
- Connection `status` values `connected` and `not_connected` / `not_configured` / `error` get their own label; any
  other value is shown as written. The `offline` kind is always shown as built in.
- `GET /decks/{id}/runs` (not in the spec) fills the activity feed with what happened before the page opened.
  Without it the feed starts empty and fills from `run.updated` events.
- "Retry" on a failed build calls `POST /decks/{id}/approve` again.
- `letter_spacing` in a rendered element is a bare number: below 1 it is read as em, otherwise as canvas px.
- In-place text editing matches the clicked box to the node field with the same text (`src/lib/edit.ts`). A box
  whose text the layout engine has altered (for example added quotation marks other than “ ”) is not editable.
- Export runs `POST /export` when the page opens, because that call is what returns the editability report.
