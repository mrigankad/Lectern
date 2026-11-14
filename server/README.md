# Lectern server

The backend of Lectern: agents plan, write, lay out and check a deck, and it exports as an editable
PowerPoint file. FastAPI + SQLModel + SQLite. The contract with the web app is `../docs/SPEC.md`.

## Run

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
cd server
uv sync
uv run uvicorn lectern.main:app --port 8000
```

The API is at `http://localhost:8000/api` (interactive docs at `/docs`). Data lives in `server/data/`
(`lectern.db` in WAL mode, exported files under `exports/`).

With no API key configured, every agent uses the built-in **offline** provider, so the product works out
of the box: it writes a deck from the prompt alone, with no network. Add a key under Connections
(`PUT /api/settings/connections`) or through an environment variable to use a model.

## Test

```sh
cd server
uv run pytest
```

The tests run offline. They ignore provider keys in your shell and use a temporary data directory.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LECTERN_DATA_DIR` | `server/data` | Where the database and exported files are stored. |
| `LECTERN_OFFLINE_DELAY` | `0.6` | Seconds the offline provider waits per agent step, so the live build has something to show. `0` in tests. |
| `LECTERN_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated origins allowed to call the API. |
| `LECTERN_REFERENCES_DIR` | `../references` | The layout, deck-type and visual knowledge the agents use. |
| `LECTERN_FORCE_OFFLINE` | unset | `1` routes every agent to the offline provider even when keys exist. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY` | unset | A key for that connection. A key saved through the API takes precedence. Keys are never returned by the API. |

### Media (images and video)

`lectern/media/` mirrors the model router: providers `higgsfield` (the Higgsfield CLI's own login; test it
under Connections to enable it, it bills credits), `google` (Imagen, Veo; `GEMINI_API_KEY`), `openai_images`
(`OPENAI_API_KEY`), `flux` (fal.ai, `FAL_KEY`), `runway` (`RUNWAYML_API_SECRET`), `stock` (Pexels,
`PEXELS_API_KEY`), uploads, and the built-in `offline` provider, which draws flat placeholders in the deck
colours. Files live in `data/media/<deck id>/`. The Art Director adds images to text-only slides only when a
media provider is connected, or with offline placeholders when `PUT /api/settings/media {"auto_images": true}`.
`LECTERN_HIGGSFIELD_BIN`, `LECTERN_HIGGSFIELD_IMAGE_MODEL` (default `gpt_image_2_5`) and
`LECTERN_HIGGSFIELD_VIDEO_MODEL` (default `seedance_2_0_mini`) override the CLI path and models.

## Layout

```
lectern/
  main.py            app factory, routers under /api, CORS, plain-language errors
  config.py          paths and environment variables
  db.py, models.py   SQLite (WAL); tables deck, slide, slide_version, run, message, finding, rule, connection, role_route
  schema.py          the scene graph and API payloads (SPEC sections 3 and 5)
  knowledge.py       parses ../references/*.md (layout patterns, deck types) for the agents
  store.py           shared reads and writes: decks, slide versions, findings, rules
  events.py          in-process pub/sub feeding the SSE endpoint
  layouts/           the 21 layouts and their slots; converting content between layouts
  engine/            place.py (Slide + Theme -> RenderedSlide on 1920x1080), lint.py (SPEC section 6),
                     text measurement, the frame and components the placers are built from
  export/            pptx.py (native text boxes, tables and charts), report.py (editability report)
  llm/               router.py (connections, presets, role -> provider/model), the Anthropic and
                     OpenAI-compatible clients, retries, and offline/ (the deterministic provider)
  agents/            strategist, writer, art_director, renderer, critic, editor, and pipeline.py
  routers/           decks, slides, ask, critic, export, settings (connections, routing, rules), layouts
scripts/
  preview.py         draw rendered slides to a PNG contact sheet (for checking placement)
  offline_demo.py    print the deck the offline provider writes for a prompt
tests/               pytest: end to end, placement invariants, lint rules, export, pipeline, providers
```

## How a deck is built

`POST /api/decks` starts the Strategist, which drafts the outline (`outline_ready`). After
`POST /api/decks/{id}/approve`, slides are built three at a time: the Writer fills the nodes and notes, the
Art Director confirms or changes the layout, the Renderer fits the content to the layout's slots, and the
Critic lints the result. A slide with a high or medium finding is sent back to the Writer once, then
re-checked. Each step is a `run` row and a `run.updated` event with a one-sentence summary; every content
change writes a `slide_version`, which is what undo restores. The user's rules are added to every agent
prompt, and a rule that bans a word is also enforced by the lint.

**Undo.** There are two undos, with one rule each:
- *Slide Undo* (`POST /decks/{id}/slides/{sid}/undo`) takes back the latest change to that slide, whoever
  made it (a manual edit, an Ask, a fix), one version at a time. It never skips over an edit to reach an
  older one.
- *Ask Undo* (`POST /decks/{id}/messages/{mid}/undo`, the Undo under a chat reply) reverts exactly the
  versions that Ask created (`message.version_ids`). For each field the Ask changed (headline, layout,
  nodes, notes, section) it puts back the value from before the Ask, unless that field was changed again
  afterwards: a later manual edit or Ask wins and is listed in `kept`. Fields the Ask did not touch are never
  written, so an earlier hand-written note survives undoing a deck-wide Ask. The revert is a new version
  ("Undid: ..."), the message is marked `undone`, and an Ask can be undone once. Removed slides are not restored.

**Refresh from sheet** (`POST .../data/refresh`) re-reads linked charts and stats and also rewrites figures
in the headline, text and notes that equal a linked value that changed (written as before: "1.6" -> "1.7",
"$1.6M" -> "$1.7M"); `text_updates` lists them, `?update_text=false` only offers them. Figures that cannot be
traced to one changed cell come back in `flagged`, and the `number_mismatch` lint compares bare decimals
("rose from 1.2 to 1.6") as well as unit figures with the slide's chart and stat values.

Runs, slides and decks that were in progress when the server stopped are marked on the next start
(the deck becomes `failed` with an explanation); `POST /approve` or `/resume` continues from the slides
that were not finished.

## Models

Routing maps each agent role to a provider and model (`GET/PUT /api/settings/routing`), with three
presets: Best quality, Balanced and Lowest cost. A role whose provider has no key falls back to the
offline provider at call time. Structured output goes through tool use (Anthropic) or function calling
(OpenAI-compatible endpoints: OpenAI, OpenRouter, Gemini, Groq, DeepSeek, Mistral, a LiteLLM gateway,
Ollama) and is validated against the agent's schema; 429, 5xx and connection errors are retried with
exponential backoff. The Critic's checks and the Renderer's fitting are deterministic code and call a
model only when a required slot has to be filled.

## MCP server (use Lectern from Claude Code, Codex, Cursor and other agents)

Lectern is also an MCP server, so an agent can make a deck without the web app. It runs two ways, on the
same engine and database:

- **stdio**: `uv --directory <path to server> run lectern-mcp`. The agent starts Lectern itself; the web
  app does not need to be running. Decks it builds appear in the web app (refresh to see them; the live
  progress view only follows builds run by the web server).
- **Streamable HTTP**: `http://localhost:8000/mcp`, served by the running API. Builds show live in the
  web app.

Tools: `create_deck` (prompt, audience, goal, minutes, tone, slide_count, `source_paths` of text files,
`interview`), `get_interview`, `answer_interview`, `skip_interview`, `get_outline`, `update_outline`,
`regenerate_outline`, `approve_outline`, `get_status` (progress and agent activity), `wait_until_ready`
(at most 600 s per call), `get_critic_report`, `fix_findings` (fix or keep), `ask` (a change in plain
language), `edit_slide` (headline, notes, layout), `list_decks`, `export_deck` (pptx; returns the path on
disk, a download link, a web link and the editability report). Resources: `lectern://decks/{id}` (the
deck JSON) and `lectern://decks/{id}/outline`.

**The outline stays a human decision.** `approve_outline` must be called explicitly. Clients should show
the user the outline (title and every headline) and wait for a yes before calling it; the server's
instructions and the tool description tell the model the same.

Setup per client (replace the path with your `server` folder; `GET /api/mcp/setup` returns these with
this machine's path filled in, and the web app shows them at `/developers`):

| Client | stdio | HTTP (server running) |
|---|---|---|
| Claude Code | `claude mcp add lectern -- uv --directory "/path/to/server" run lectern-mcp` | `claude mcp add --transport http lectern http://localhost:8000/mcp` |
| Claude desktop | `claude_desktop_config.json`: `{"mcpServers": {"lectern": {"command": "uv", "args": ["--directory", "/path/to/server", "run", "lectern-mcp"]}}}` | use stdio |
| Codex | `~/.codex/config.toml`: `[mcp_servers.lectern]` `command = "uv"` `args = ["--directory", "/path/to/server", "run", "lectern-mcp"]` | `[mcp_servers.lectern]` `url = "http://localhost:8000/mcp"` |
| Cursor | `.cursor/mcp.json`: same `mcpServers` JSON as Claude desktop | `{"mcpServers": {"lectern": {"url": "http://localhost:8000/mcp"}}}` |
| Gemini CLI | `~/.gemini/settings.json`: same `mcpServers` JSON | `{"mcpServers": {"lectern": {"httpUrl": "http://localhost:8000/mcp"}}}` |
| Antigravity | `mcp_config.json` (Agent panel > MCP servers > Manage > View raw config): same `mcpServers` JSON | `{"mcpServers": {"lectern": {"serverUrl": "http://localhost:8000/mcp"}}}` |

The HTTP endpoint accepts requests from localhost only and has no authentication: keep the API on
localhost. `LECTERN_WEB_URL` (default `http://localhost:3000`), `LECTERN_API_URL` (default
`http://localhost:8000`) and `LECTERN_MCP_URL` (default `http://localhost:8000/mcp`) set the links the
tools return and the setup shows.

## PDF, images, notes and brand kits

`POST /api/decks/{id}/export` also takes `format: "pdf" | "images" | "notes"`: a vector PDF drawn with reportlab
(`export/pdf.py`; 960x540 pt pages, Urbanist embedded, charts and tables as paths, optional notes page per slide),
a zip of 1920x1080 PNGs (the PDF rasterised with pdfium) and a Markdown speaker script.
Urbanist (OFL, `lectern/assets/fonts/OFL.txt`) is bundled as static Regular and Bold instances of the Google Fonts
variable font. It is **not** embedded in .pptx files: python-pptx has no font-embedding API, and PowerPoint's embedded
fonts are obfuscated `.fntdata` parts plus `p:embeddedFontLst` entries that only PowerPoint itself writes reliably.
A machine without Urbanist shows the PowerPoint file in a fallback font; the PDF always looks right.

Brand kits (`brand/`, `routers/brand.py`, table `brand_kit`, files in `data/brand/{id}/`): upload a .potx/.pptx
(and optionally a brand PDF) to `POST /api/brand-kits`; Lectern reads the colour scheme, fonts, master/layout pictures
(logos) and layouts, builds a theme, and suggests plain-language rules (colours, font, logo, min size) that the lint
checks as `brand` findings. `PUT /api/decks/{id}/brand-kit` applies a kit; `GET /api/decks/{id}/brand-match` scores it;
the .pptx export of a branded deck is built on the uploaded template's master and Blank layout.
