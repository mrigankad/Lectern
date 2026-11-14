# Lectern

Lectern turns a prompt, plus your spreadsheets, documents and links, into a finished presentation. You can edit every part of it and export it as PowerPoint, PDF or slide images.

It is a full product with a web app and a backend engine, not a chat skill. Agents plan, write, lay out and check the deck. You approve the outline and stay in control of every slide.

## How it works

1. **Brief.** Describe the deck, or attach data and documents.
2. **Interview.** The Strategist asks only the questions your brief left open: audience, goal and length.
3. **Outline.** Review and reorder the storyline, then approve it. Nothing is built until you approve.
4. **Build.** The agents fill the slides live, and you can pause and resume.
   - The Analyst computes every number from real cells in your data.
   - The Writer drafts the text and the Art Director picks the layout and visuals.
   - The Critic lints each slide and sends weak ones back.
5. **Edit.** Ask in chat ("make slide 4 punchier", "shorten the deck"), edit directly, or refresh linked data. Undo reverts one edit at a time.
6. **Export and share.** Export as editable PPTX with native charts, tables and text, as PDF, as PNG slides or as speaker notes. You can also present in the browser or share a link.

Every slide is a typed scene graph placed on a 1920×1080 canvas. The web view, PowerPoint, PDF and images are all rendered from that same source, so they always match.

## What's inside

| Folder | What it is |
|---|---|
| `server/` | FastAPI + SQLModel engine: agents, 21 layouts, the Critic, exporters, brand kits (from `.potx`), data sources with linked charts, the media router, share links and an MCP server. |
| `web/` | Next.js 15 app: new deck, interview, outline, editor, data studio, media, sources, brand kits, connections, present mode and the public share viewer. |
| `docs/SPEC.md` | The contract between the backend and the web app: scene graph, API, events, lint rules and providers. |
| `references/` | Layout, deck-type and visual-design knowledge the agents draw on. |

## Integrations

- **Models:** Claude Code (uses your local `claude` login), Anthropic, OpenRouter, LiteLLM and any OpenAI-compatible gateway, plus a built-in offline mode that needs no key.
- **Images and video:** Higgsfield, Google Imagen and Veo, OpenAI Images, FLUX, Runway, Pexels stock photos, and your own uploads.
- **Agents:** an MCP server (`uv run lectern-mcp`, or HTTP at `/mcp`) lets Claude Code, Codex, Antigravity and other agents create and edit decks. Approving the outline always stays with a person.

Add keys on the **Connections** page. Keys stay on your machine.

## Run it

You need Python 3.12+ with [uv](https://docs.astral.sh/uv/), and Node 20+ with pnpm.

```sh
# Backend: http://localhost:8000 (API docs at /docs)
cd server
uv sync
uv run uvicorn lectern.main:app --port 8000

# Web app: http://localhost:3000
cd web
pnpm install
pnpm dev
```

`pnpm dev:mock` runs the web app without the backend, on mock data.

The backend works out of the box with the offline provider. Connect a model to get real writing.

## Test

```sh
cd server && uv run pytest              # backend tests, run offline
cd web && pnpm typecheck && pnpm lint
```

See `server/README.md` for the environment variables.
