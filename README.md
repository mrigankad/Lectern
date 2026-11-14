<p align="center">
  <img src="docs/readme/hero.png" alt="Lectern: say the thing, we build the room around it" width="100%" />
</p>

<p align="center">
  <a href="#how-it-works">How it works</a> ·
  <a href="#screens">Screens</a> ·
  <a href="#integrations">Integrations</a> ·
  <a href="#run-it">Run it</a> ·
  <a href="docs/SPEC.md">Spec</a>
</p>

Lectern turns a prompt, plus your spreadsheets, documents and links, into a finished presentation. You can edit every part of it and export it as PowerPoint, PDF or slide images.

It is a full product with a web app and a backend engine, not a chat skill. Agents plan, write, design and check the deck. You approve the outline and stay in control of every slide.

<p align="center">
  <img src="docs/readme/screens/07-editor.png" alt="The Lectern editor: slide rail, canvas, speaker notes and the Ask panel" width="100%" />
  <br/><sub>The editor. Ask for changes in plain words, and every change can be undone.</sub>
</p>

## How it works

<p align="center">
  <img src="docs/readme/how-it-works.png" alt="Brief, interview, outline, build, critic, export" width="100%" />
</p>

<table>
  <tr>
    <td width="33%"><img src="docs/readme/screens/04-interview.png" alt="Strategist interview" /></td>
    <td width="33%"><img src="docs/readme/screens/05-outline.png" alt="Outline review" /></td>
    <td width="33%"><img src="docs/readme/screens/06-live-build.png" alt="Live build" /></td>
  </tr>
  <tr>
    <td><b>Interview.</b> The Strategist asks only what your brief left open: audience, goal and length.</td>
    <td><b>Outline.</b> Reorder the storyline and approve it. Nothing is built before you do.</td>
    <td><b>Live build.</b> Watch the agents fill each slide. Pause and resume at any point.</td>
  </tr>
</table>

- **Analyst** computes every number from real cells in your data, so figures trace back to a source.
- **Writer** drafts headlines as claims, body text and speaker notes.
- **Art Director** picks one of 21 layouts, the chart type and the visuals.
- **Critic** lints every slide (overflow, contrast, untraceable numbers, template text) and sends weak ones back.
- **Editor** applies chat requests to one slide or the whole deck, one undoable step at a time.

Every slide is a typed scene graph on a 1920×1080 canvas. The web view, PowerPoint, PDF and images are all rendered from that one source, so they always match.

## Screens

<table>
  <tr>
    <td width="50%"><img src="docs/readme/screens/02-home.png" alt="Home and deck library" /><br/><b>Home.</b> Your decks, with a custom icon for each.</td>
    <td width="50%"><img src="docs/readme/screens/03-new-deck.png" alt="New deck" /><br/><b>New deck.</b> A prompt, attachments, audience and length.</td>
  </tr>
  <tr>
    <td><img src="docs/readme/screens/08-critic.png" alt="Critic report" /><br/><b>Critic report.</b> Every issue, with a one-click fix.</td>
    <td><img src="docs/readme/screens/10-data.png" alt="Data and charts" /><br/><b>Data studio.</b> Charts linked to sheet ranges that refresh with the data.</td>
  </tr>
  <tr>
    <td><img src="docs/readme/screens/09-brand-kit.png" alt="Brand kit" /><br/><b>Brand kit.</b> Import a <code>.potx</code> for your fonts, colours and logo.</td>
    <td><img src="docs/readme/screens/11-media.png" alt="Media studio" /><br/><b>Media studio.</b> Generate images and video, or pick stock photos.</td>
  </tr>
  <tr>
    <td><img src="docs/readme/screens/12-connections.png" alt="Connections and model routing" /><br/><b>Connections.</b> Choose a model for each agent, and add keys.</td>
    <td><img src="docs/readme/screens/13-export.png" alt="Export" /><br/><b>Export.</b> PPTX, PDF, PNG and notes, all editable.</td>
  </tr>
  <tr>
    <td><img src="docs/readme/screens/14-share.png" alt="Share link" /><br/><b>Share.</b> A read-only link, with an expiry if you want one.</td>
    <td><img src="docs/readme/screens/15-present.png" alt="Present mode" /><br/><b>Present.</b> Full screen, with notes and a timer.</td>
  </tr>
  <tr>
    <td><img src="docs/readme/screens/01-welcome.png" alt="Welcome" /><br/><b>Welcome.</b> Connect a model, or start offline.</td>
    <td><img src="docs/readme/screens/16-agents.png" alt="From Claude Code and other agents" /><br/><b>From agents.</b> Drive Lectern from Claude Code, Codex or Antigravity.</td>
  </tr>
</table>

<sub>These are the product designs from the Lectern Paper file. Invite by email, comments and Google Slides export are designed but not built yet.</sub>

<details>
<summary><b>Full flow map</b></summary>
<br/>
<img src="docs/readme/screens/00-flow-map.png" alt="Lectern flow map" width="100%" />
</details>

## Integrations

<p align="center">
  <img src="docs/readme/whats-inside.png" alt="Models, images and video, agents, exports" width="100%" />
</p>

Add provider keys on the **Connections** page. Keys stay on your machine. The MCP server runs with `uv run lectern-mcp`, or over HTTP at `/mcp`. It never approves an outline on its own.

## Repository

| Folder | What it is |
|---|---|
| `server/` | FastAPI + SQLModel engine: agents, 21 layouts, the Critic, exporters, brand kits from `.potx`, linked data sources, media router, share links and MCP server. |
| `web/` | Next.js 15 app: every screen above, plus present mode and the public share viewer. |
| `docs/SPEC.md` | The contract between the backend and the web app. |
| `references/` | Layout, deck-type and visual-design knowledge the agents draw on. |

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

`pnpm dev:mock` runs the web app on mock data without the backend. Without any key, the backend uses its offline provider. Connect a model to get real writing.

## Test

```sh
cd server && uv run pytest              # backend tests, run offline
cd web && pnpm typecheck && pnpm lint
```

See `server/README.md` for environment variables.
