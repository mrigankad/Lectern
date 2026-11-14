"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight, Braces, Check, ChevronRight, Code, Copy, ExternalLink, Monitor, MousePointer2, Plug, Sparkle,
  SquareTerminal, Triangle, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/Shell";
import { Card, ErrorState, LoadingState, PageHeader, Pill, Segmented } from "@/components/ui";
import { API_URL, api, errorText, keys, type McpClientSetup } from "@/lib/api";
import { cx } from "@/lib/format";
import { ProviderLogo, logoFor } from "@/components/ProviderLogo";

const ICONS: Record<string, LucideIcon> = {
  claude_code: SquareTerminal, claude_desktop: Monitor, codex: Code, antigravity: Triangle, cursor: MousePointer2,
  gemini_cli: Sparkle,
};

type Transport = "stdio" | "http";

/** An illustrative run, as an agent shows it. Not live data. */
const EXAMPLE = [
  { tool: "create_deck", title: "Outline drafted: Release 4.2", detail: "From the prompt and CHANGELOG.md, passed as a source file" },
  { tool: "approve_outline", title: "Outline approved by you", detail: "The agent shows you the outline first and waits for your yes", approved: true },
  { tool: "wait_until_ready", title: "7 slides built", detail: "Writer, Art Director, Renderer and Critic, three slides at a time" },
  { tool: "get_critic_report", title: "Critic score and findings", detail: "fix_findings repairs them, or keeps the ones you meant" },
  { tool: "export_deck", title: "Exported Release 4.2.pptx", detail: "Editable PowerPoint; the path on disk and a link back to Lectern" },
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1600);
        });
      }}
      className="inline-flex h-11 shrink-0 items-center gap-2 rounded-control border border-line bg-bg px-3.5 text-[14px] font-bold text-ink hover:border-line-strong"
    >
      {copied ? <Check size={16} className="text-pass" aria-hidden /> : <Copy size={16} aria-hidden />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Tile({ icon: Icon, logo, name, where, active, onClick, href }: {
  icon: LucideIcon; logo?: string; name: string; where: string; active?: boolean; onClick?: () => void; href?: string;
}) {
  const body = (
    <>
      {logo && logoFor(logo) ? <ProviderLogo id={logo} label={name} size={24} /> : <Icon size={18} className="shrink-0 text-ink" aria-hidden />}
      <span className="flex min-w-0 flex-col">
        <span className="text-[14px] font-bold leading-5 text-ink">{name}</span>
        <span className="truncate text-[12px] leading-4 text-body">{where}</span>
      </span>
    </>
  );
  const cls = cx(
    "flex h-14 items-center gap-3 rounded-card border bg-bg px-3.5 text-left transition-colors",
    active ? "border-action shadow-[0_0_0_1px_var(--action)]" : "border-line hover:border-line-strong",
  );
  return href ? (
    <a href={href} target="_blank" rel="noreferrer" className={cls}>{body}</a>
  ) : (
    <button type="button" aria-pressed={active} onClick={onClick} className={cls}>{body}</button>
  );
}

function Snippet({ client, transport }: { client: McpClientSetup; transport: Transport }) {
  const text = transport === "http" && client.http ? client.http : client.stdio;
  const oneLine = !text.includes("\n");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <pre
          className={cx(
            "min-w-0 grow overflow-x-auto rounded-control border border-line bg-surface px-3 py-3 text-[13px] leading-[18px] text-ink",
            oneLine && "flex items-center gap-2 whitespace-nowrap",
          )}
        >
          {oneLine ? <ChevronRight size={14} className="shrink-0 text-body" aria-hidden /> : null}
          <code>{text}</code>
        </pre>
        <CopyButton text={text} />
      </div>
      <p className="text-[12px] leading-4 text-body">
        {client.file ? <>Add to <span className="font-bold text-ink">{client.file}</span>, then restart {client.name}.</> : "Run it in your terminal, in any folder."}
        {transport === "http" && !client.http ? ` ${client.name} connects by starting Lectern itself, so this uses the local command.` : ""}
      </p>
    </div>
  );
}

export default function DevelopersPage() {
  const setup = useQuery({ queryKey: keys.mcpSetup, queryFn: api.getMcpSetup });
  const [picked, setPicked] = useState("claude_code");
  const [transport, setTransport] = useState<Transport>("stdio");
  const clients = setup.data?.clients ?? [];
  const client = clients.find((c) => c.id === picked) ?? clients[0];

  return (
    <AppShell crumbs={[{ label: "Settings" }, { label: "Connections and models", href: "/connections" }, { label: "From Claude Code and other agents" }]}>
      <PageHeader
        icon={<SquareTerminal size={20} />}
        title="Make a deck from Claude Code or any agent"
        subtitle="For developers. Ask in the tool you already use. Lectern builds the deck in the background and returns an editable file."
        actions={<Pill>Without the web app</Pill>}
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_468px]">
        <section aria-label="Example run" className="flex flex-col overflow-hidden rounded-card bg-ink text-white">
          <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-3.5">
            <SquareTerminal size={16} aria-hidden />
            <span className="text-[14px] font-bold">Claude Code</span>
            <span className="text-[13px] text-white/60">Example run</span>
          </div>
          <div className="flex flex-col gap-4 p-5">
            <div className="flex items-center gap-3 rounded-control border border-white/10 bg-white/5 px-4 py-3">
              <ChevronRight size={16} className="text-white/70" aria-hidden />
              <span className="text-[15px] font-bold">Make the release deck from this repo</span>
            </div>
            <p className="text-[14px] leading-5 text-white/85">
              I will read the changelog, then build the deck with Lectern.
            </p>
            <ol className="flex flex-col">
              {EXAMPLE.map((step) => (
                <li key={step.tool} className="grid grid-cols-[20px_150px_minmax(0,1fr)_auto] items-center gap-3 border-t border-white/10 py-4">
                  <Check size={14} className="rounded-pill bg-pass/25 p-0.5 text-pass" aria-hidden />
                  <span className="truncate text-[13px] text-white/70">lectern · {step.tool}</span>
                  <span className="flex min-w-0 flex-col">
                    <span className="text-[14px] font-bold leading-5">{step.title}</span>
                    <span className="text-[13px] leading-[18px] text-white/65">{step.detail}</span>
                  </span>
                  {step.approved ? <Pill tone="pass">You approved</Pill> : <span />}
                </li>
              ))}
            </ol>
            <p className="flex items-center gap-2 border-t border-white/10 pt-4 text-[13px] text-white/80">
              <ExternalLink size={14} aria-hidden />
              Every result carries a link that opens the deck here in Lectern.
            </p>
          </div>
        </section>

        <div className="flex min-w-0 flex-col gap-5">
          <section aria-labelledby="works-with" className="flex flex-col gap-2.5">
            <h2 id="works-with" className="text-[15px] font-bold leading-5 text-ink">Works with</h2>
            {setup.isPending ? (
              <LoadingState label="Loading setup" className="py-8" />
            ) : setup.isError ? (
              <ErrorState title="Setup could not be loaded" message={errorText(setup.error)} onRetry={() => setup.refetch()} />
            ) : (
              <div className="grid grid-cols-2 gap-2.5">
                {clients.map((c) => (
                  <Tile key={c.id} icon={ICONS[c.id] ?? Plug} logo={c.id} name={c.name} where={c.where} active={c.id === client?.id}
                    onClick={() => setPicked(c.id)} />
                ))}
                <Tile icon={Plug} logo="mcp" name="Any MCP client" where="One standard connection" active={false}
                  onClick={() => { setTransport("http"); setPicked("cursor"); }} />
                <Tile icon={Braces} name="REST API" where="From your own code" href={`${API_URL || "http://localhost:8000"}/docs`} />
              </div>
            )}
          </section>

          {client ? (
            <Card className="flex flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-[15px] font-bold leading-5 text-ink">Set up {client.name}</h2>
                <Segmented<Transport>
                  label="How the agent reaches Lectern"
                  value={transport}
                  onChange={setTransport}
                  options={[{ value: "stdio", label: "Local command" }, { value: "http", label: "Running server" }]}
                />
              </div>
              <Snippet client={client} transport={transport} />
              <p className="text-[12px] leading-4 text-body">
                {transport === "stdio" ? setup.data?.stdio.note : `${setup.data?.http.url} · ${setup.data?.http.note}`}
              </p>
            </Card>
          ) : null}

          <Card className="flex flex-col gap-2.5 p-4">
            <h2 className="text-[15px] font-bold leading-5 text-ink">What comes back</h2>
            <ul className="flex flex-col gap-1.5 text-[13px] leading-[19px] text-body">
              <li><span className="font-bold text-ink">The outline, for you to approve.</span> The agent shows it to you; nothing is built until you say yes.</li>
              <li><span className="font-bold text-ink">Progress and the Critic report.</span> Status, what each agent did, scores and findings to fix or keep.</li>
              <li><span className="font-bold text-ink">An editable .pptx.</span> The path on disk, a download link and how many objects are native text boxes, charts and tables.</li>
            </ul>
          </Card>

          <div className="flex items-start gap-3 rounded-card bg-surface p-4 text-[14px] font-bold leading-5 text-ink">
            <ArrowLeftRight size={18} className="mt-0.5 shrink-0" aria-hidden />
            Same engine, same decks. Anything an agent builds shows up in your Lectern home, ready to edit or export.
          </div>
        </div>
      </div>
    </AppShell>
  );
}
