// DEVELOPMENT MOCK ONLY. Reached through the /api rewrite when the app runs with `pnpm dev:mock`
// (LECTERN_MOCK=1). In every other mode this route answers 404 and /api is proxied to the real API.

import { NextResponse, type NextRequest } from "next/server";
import * as store from "@/mock/store";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ENABLED = process.env.LECTERN_MOCK === "1";

function sse(deckId: string, signal: AbortSignal) {
  const encoder = new TextEncoder();
  let cleanup = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (event: string, data: unknown) => {
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        } catch {
          cleanup();
        }
      };
      const off = store.subscribe(deckId, send);
      const ping = setInterval(() => send("ping", {}), 20_000);
      cleanup = () => {
        off();
        clearInterval(ping);
      };
      signal.addEventListener("abort", () => {
        cleanup();
        try {
          controller.close();
        } catch {}
      });
      send("ping", {});
    },
    cancel() {
      cleanup();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive", "X-Accel-Buffering": "no" },
  });
}

async function handle(req: NextRequest, path: string[]): Promise<Response> {
  if (!ENABLED) return NextResponse.json({ detail: "The mock API is switched off. Start the app with pnpm dev:mock to use it." }, { status: 404 });
  const method = req.method;
  const body = method === "GET" || method === "DELETE" ? undefined : await req.json().catch(() => ({}));
  const [a, b, c, d, e] = path;
  const is = (m: string, ...parts: (string | undefined)[]) =>
    method === m && parts.length === path.length && parts.every((p, i) => p === undefined || p === path[i]);

  try {
    // A little latency so loading states can be seen.
    await new Promise((r) => setTimeout(r, 180));
    let out: unknown;
    if (is("GET", "health")) out = store.health();
    else if (is("GET", "decks")) out = store.listDecks();
    else if (is("POST", "decks")) out = store.createDeck(body);
    else if (is("GET", "decks", undefined)) out = store.getDeck(b);
    else if (is("PATCH", "decks", undefined)) out = store.patchDeck(b, body);
    else if (is("DELETE", "decks", undefined)) out = store.deleteDeck(b);
    else if (is("PUT", "decks", undefined, "outline")) out = store.putOutline(b, body);
    else if (is("POST", "decks", undefined, "outline", "regenerate")) out = store.regenerate(b, body?.instruction);
    else if (is("POST", "decks", undefined, "approve")) out = store.approve(b);
    else if (is("POST", "decks", undefined, "pause")) out = store.setPaused(b, true);
    else if (is("POST", "decks", undefined, "resume")) out = store.setPaused(b, false);
    else if (is("GET", "decks", undefined, "render")) out = store.render(b);
    else if (is("GET", "decks", undefined, "slides", undefined, "render")) out = store.renderSlide(b, d);
    else if (is("PATCH", "decks", undefined, "slides", undefined)) out = store.patchSlide(b, d, body);
    else if (is("POST", "decks", undefined, "slides", undefined, "undo")) out = store.undoSlide(b, d);
    else if (is("POST", "decks", undefined, "ask")) out = store.ask(b, body);
    else if (is("GET", "decks", undefined, "messages")) out = store.getMessages(b);
    else if (is("POST", "decks", undefined, "messages", undefined, "undo")) out = store.undoMessage(b, d);
    else if (is("GET", "decks", undefined, "critic")) out = store.critic(b);
    else if (is("POST", "decks", undefined, "critic", "findings", undefined)) out = store.actOnFinding(b, e, body?.action);
    else if (is("POST", "decks", undefined, "critic", "fix-all")) out = store.fixAll(b);
    else if (is("POST", "decks", undefined, "export")) out = store.exportDeck(b, body?.include_notes !== false);
    else if (is("GET", "decks", undefined, "events")) {
      store.getDeck(b);
      return sse(b, req.signal);
    } else if (is("GET", "rules")) out = store.listRules();
    else if (is("POST", "rules")) out = store.addRule(body?.text);
    else if (is("DELETE", "rules", undefined)) out = store.deleteRule(b);
    else if (is("GET", "files", undefined)) {
      const f = store.file(b);
      return new Response(f.body, {
        headers: { "Content-Type": "text/plain; charset=utf-8", "Content-Disposition": `attachment; filename="${f.filename}"` },
      });
    } else if (is("GET", "layouts")) out = store.layouts();
    else if (is("GET", "settings", "connections")) out = store.getConnections();
    else if (is("PUT", "settings", "connections")) out = store.putConnection(body);
    else if (is("POST", "settings", "connections", undefined, "test")) out = store.testConnection(c);
    else if (is("GET", "settings", "routing")) out = store.getRouting();
    else if (is("PUT", "settings", "routing")) out = store.putRouting(body);
    else return NextResponse.json({ detail: `The mock API has no ${method} /${[a, ...path.slice(1)].join("/")}.` }, { status: 404 });
    return NextResponse.json(out);
  } catch (err) {
    if (err instanceof store.MockError) return NextResponse.json({ detail: err.message }, { status: err.status });
    console.error("[mock-api]", err);
    return NextResponse.json({ detail: "The mock API hit an unexpected error. See the terminal." }, { status: 500 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };
const route = async (req: NextRequest, ctx: Ctx) => handle(req, (await ctx.params).path);

export { route as GET, route as POST, route as PUT, route as PATCH, route as DELETE };
