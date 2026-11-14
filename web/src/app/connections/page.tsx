"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Compass, Eye, Globe, HardDrive, Layers, LayoutTemplate, MessageSquare, Pencil, Plug, Sparkles, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { AppShell } from "@/components/Shell";
import { ProviderLogo, logoFor } from "@/components/ProviderLogo";
import { Button, Card, Combobox, Dropdown, ErrorState, InlineError, LoadingState, PageHeader, Pill, type Tone } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { cx, providerName, roleName } from "@/lib/format";
import type { Connection, ConnectionTest, Role, RoleRoute, Routing, RoutingPreset } from "@/lib/types";

const ROLES: { role: Role; icon: LucideIcon; job: string }[] = [
  { role: "strategist", icon: Compass, job: "Works out what the deck must say, and in what order" },
  { role: "writer", icon: Pencil, job: "Writes headlines, slide text and speaker notes" },
  { role: "art_director", icon: LayoutTemplate, job: "Chooses layouts, pictures and chart types" },
  { role: "renderer", icon: Layers, job: "Builds each slide as an editable file" },
  { role: "critic", icon: Eye, job: "Checks every slide and sends back fixes" },
  { role: "editor", icon: MessageSquare, job: "Makes the changes you ask for in chat" },
];

const DEFAULT_PRESETS = [
  { id: "best_quality", label: "Best quality", description: "Best quality uses the strongest model for every job." },
  { id: "balanced", label: "Balanced", description: "Balanced uses the strongest model only where it matters most." },
  { id: "lowest_cost", label: "Lowest cost", description: "Lowest cost uses the smallest model that can do each job." },
];

function statusOf(c: Connection): { label: string; tone: Tone; ok: boolean } {
  if (c.kind === "offline" || c.id === "offline") return { label: "Built in", tone: "pass", ok: true };
  const s = c.status.toLowerCase();
  if (s === "connected" || s === "ok" || s === "ready") return { label: "Connected", tone: "pass", ok: true };
  if (s === "error" || s === "failed" || s === "invalid") return { label: "Not working", tone: "fail", ok: false };
  if (s === "not_connected" || s === "not_configured" || s === "missing_key" || s === "disconnected" || s === "unconfigured") return { label: "Not connected", tone: "neutral", ok: false };
  return { label: c.status.replace(/_/g, " "), tone: "neutral", ok: false };
}

function describe(c: Connection): string {
  if (c.detail) return c.detail;
  if (c.kind === "offline") return "No key and no network. Makes a sensible deck from your prompt.";
  if (c.kind === "anthropic") return c.has_key ? "Claude models · key saved" : "Paste a key to use Claude models";
  if (c.kind === "media") return c.has_key ? "Pictures and video · key saved" : "Paste a key to make pictures or video";
  if (c.kind === "gemini") return c.has_key ? "Gemini models · key saved" : "Paste a key to use Gemini models";
  return c.base_url ? `${c.base_url}${c.has_key ? " · key saved" : ""}` : "Any OpenAI-compatible endpoint";
}

function ConnectionRow({ c, onModels }: { c: Connection; onModels: (id: string, models: string[]) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(c.base_url ?? "");
  const [tested, setTested] = useState<ConnectionTest | null>(null);
  const status = statusOf(c);
  const offline = c.kind === "offline" || c.id === "offline";
  const hasUrl = c.kind === "openai_compatible" || Boolean(c.base_url);
  const Icon = offline ? HardDrive : c.kind === "openai_compatible" ? Globe : Sparkles;

  const save = useMutation({
    mutationFn: () => api.putConnection({ id: c.id, ...(key.trim() ? { api_key: key.trim() } : {}), ...(hasUrl ? { base_url: baseUrl.trim() } : {}) }),
    onSuccess: () => {
      setKey("");
      qc.invalidateQueries({ queryKey: keys.connections });
      qc.invalidateQueries({ queryKey: keys.health });
    },
  });
  const test = useMutation({
    mutationFn: () => api.testConnection(c.id),
    onSuccess: (r) => {
      setTested(r);
      if (r.models?.length) onModels(c.id, r.models);
      qc.invalidateQueries({ queryKey: keys.connections });
    },
  });

  return (
    <li className="border-t border-line">
      <div className="flex items-center gap-3 px-4 py-3">
        {!offline && logoFor(c.id) ? <ProviderLogo id={c.id} label={c.label} size={24} /> : <Icon size={18} className="shrink-0 text-body" aria-hidden />}
        <div className="flex min-w-0 grow flex-col">
          <span className="text-[15px] font-bold leading-5 text-ink">{c.label}</span>
          <span className="truncate text-[13px] leading-[18px] text-body">{describe(c)}</span>
        </div>
        <Pill tone={status.tone}>{status.label}</Pill>
        <div className="flex w-[84px] shrink-0 justify-end">
          <Button size="sm" variant={status.ok ? "ghost" : "secondary"} aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Close" : offline ? "Test" : status.ok ? "Manage" : "Connect"}
          </Button>
        </div>
      </div>
      {open ? (
        <div className="flex flex-col gap-3 bg-surface px-4 pb-4 pt-3">
          {!offline ? (
            <div className="flex flex-wrap gap-3">
              <label className="flex min-w-[220px] grow basis-0 flex-col gap-1 text-[12px] text-body">
                API key
                <input
                  type="password"
                  autoComplete="off"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder={c.has_key ? "A key is saved. Paste a new one to replace it" : "Paste the key"}
                  className="h-9 rounded-control border border-line-strong bg-bg px-3 text-[14px] text-ink placeholder:text-muted focus:border-action"
                />
              </label>
              {hasUrl ? (
                <label className="flex min-w-[220px] grow basis-0 flex-col gap-1 text-[12px] text-body">
                  Base URL
                  <input
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="https://api.example.com/v1"
                    className="h-9 rounded-control border border-line-strong bg-bg px-3 text-[14px] text-ink placeholder:text-muted focus:border-action"
                  />
                </label>
              ) : null}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {!offline ? (
              <Button size="sm" variant="primary" busy={save.isPending} disabled={!key.trim() && baseUrl.trim() === (c.base_url ?? "")} onClick={() => save.mutate()}>
                Save
              </Button>
            ) : null}
            <Button size="sm" busy={test.isPending} onClick={() => test.mutate()}>
              Test connection
            </Button>
            {!offline ? <span className="text-[12px] leading-4 text-body">Keys are stored on the server and never shown again.</span> : null}
          </div>
          <InlineError>{save.isError ? errorText(save.error) : test.isError ? errorText(test.error) : null}</InlineError>
          {tested ? (
            <div className={cx("rounded-control px-3 py-2.5 text-[13px] leading-[19px] text-ink", tested.ok ? "bg-pass-soft" : "bg-fail-soft")} role="status">
              <span className="font-bold">{tested.ok ? "It works." : "It did not work."}</span> {tested.detail}
              {tested.models?.length ? <div className="pt-1 text-body">Models: {tested.models.slice(0, 12).join(", ")}{tested.models.length > 12 ? " and more" : ""}</div> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

function RoleRow({
  role, icon: Icon, job, route, connections, models, disabled, onChange,
}: {
  role: Role; icon: LucideIcon; job: string; route: RoleRoute | undefined; connections: Connection[];
  models: string[]; disabled: boolean; onChange: (next: RoleRoute) => void;
}) {
  const provider = route?.provider ?? "";
  const [draft, setDraft] = useState<{ value: string; from: string } | null>(null);
  const saved = route?.model ?? "";
  const model = draft && draft.from === `${provider}:${saved}` ? draft.value : saved;
  const known = connections.some((c) => c.id === provider);
  const commit = () => {
    if (model.trim() && model.trim() !== saved) onChange({ provider, model: model.trim() });
    else setDraft(null);
  };
  return (
    <li className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-t border-line px-4 py-2.5">
      <Icon size={18} className="shrink-0 text-body" aria-hidden />
      <span className="w-[104px] shrink-0 text-[15px] font-bold leading-5 text-ink">{roleName(role)}</span>
      <span className="min-w-[160px] grow basis-0 text-[13px] leading-[19px] text-body">{job}</span>
      <div className="flex shrink-0 items-center gap-2">
        <Dropdown
          ariaLabel={`Provider for the ${roleName(role)}`}
          value={provider}
          disabled={disabled}
          onChange={(v) => onChange({ provider: v, model: "" })}
          className="w-[170px]"
          minMenuWidth={220}
          options={[
            ...(!known && provider ? [{ value: provider, label: providerName(provider) }] : []),
            ...connections.map((c) => ({
              value: c.id,
              label: c.label,
              icon: <ProviderLogo id={c.id} label={c.label} size={20} />,
              hint: statusOf(c).ok ? undefined : "Not connected",
            })),
          ]}
        />
        <Combobox
          ariaLabel={`Model for the ${roleName(role)}`}
          value={model}
          disabled={disabled}
          suggestions={models}
          onChange={(v) => setDraft({ value: v, from: `${provider}:${saved}` })}
          onCommit={commit}
          placeholder="Model name"
          className="w-[220px]"
        />
      </div>
    </li>
  );
}

export default function ConnectionsPage() {
  const qc = useQueryClient();
  const connections = useQuery({ queryKey: keys.connections, queryFn: api.getConnections });
  const routing = useQuery({ queryKey: keys.routing, queryFn: api.getRouting });
  const [discovered, setDiscovered] = useState<Record<string, string[]>>({});

  const update = useMutation({
    mutationFn: (body: Partial<Routing>) => api.putRouting(body),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.routing });
      qc.invalidateQueries({ queryKey: keys.health });
    },
  });

  const all = connections.data ?? [];
  const list = all.filter((c) => c.kind !== "media");
  const media = all.filter((c) => c.kind === "media");
  const ready = list.filter((c) => statusOf(c).ok).length;
  const r = routing.data;
  const presets = ((r?.presets?.length ? r.presets : DEFAULT_PRESETS) as RoutingPreset[])
    .map((p) => ({ id: String(p.id ?? p.name ?? ""), label: String(p.label ?? p.name ?? p.id ?? ""), description: typeof p.description === "string" ? p.description : "" }))
    .filter((p) => p.id);
  const active = presets.find((p) => p.id === r?.preset);

  const modelsFor = (provider: string): string[] => {
    const used = r ? Object.values(r.roles).filter((x) => x.provider === provider).map((x) => x.model) : [];
    return [...new Set([...(discovered[provider] ?? []), ...used])].filter(Boolean);
  };

  function setRole(role: Role, next: RoleRoute) {
    if (!r) return;
    const model = next.model || modelsFor(next.provider)[0] || "";
    if (!model) {
      // No model known for this provider yet: keep the choice on screen and let the person type one.
      qc.setQueryData<Routing>(keys.routing, { ...r, preset: "custom", roles: { ...r.roles, [role]: { provider: next.provider, model: "" } } });
      return;
    }
    update.mutate({ preset: "custom", roles: { ...r.roles, [role]: { provider: next.provider, model } } });
  }

  return (
    <AppShell crumbs={[{ label: "Settings" }, { label: "Connections and models" }]}>
      <PageHeader
        icon={<Plug size={22} />}
        title="Connections and model routing"
        subtitle="Bring your own models and choose which one does each job."
        actions={
          <span className="flex items-center gap-1.5 text-[13px] text-body" role="status">
            {update.isPending ? "Saving" : update.isError ? <span className="text-fail">Not saved</span> : (<><Check size={15} className="text-pass" aria-hidden /> All changes saved</>)}
          </span>
        }
      />
      <div className="flex flex-wrap items-start gap-4">
        <Card className="min-w-[380px] grow basis-0 overflow-hidden">
          <div className="flex items-baseline justify-between px-4 pb-2.5 pt-3.5">
            <h2 className="text-[15px] font-bold leading-5 text-ink">Models</h2>
            {connections.data ? <span className="text-[12px] text-body">{ready} of {list.length} ready</span> : null}
          </div>
          {connections.isPending ? (
            <LoadingState label="Loading connections" className="border-t border-line py-10" />
          ) : connections.isError ? (
            <div className="border-t border-line p-4">
              <ErrorState title="Connections could not be loaded" message={errorText(connections.error)} onRetry={() => connections.refetch()} />
            </div>
          ) : list.length === 0 ? (
            <p className="border-t border-line px-4 py-4 text-[13px] text-body">The server lists no model providers.</p>
          ) : (
            <ul>
              {list.map((c) => (
                <ConnectionRow key={c.id} c={c} onModels={(cid, models) => setDiscovered((d) => ({ ...d, [cid]: models }))} />
              ))}
            </ul>
          )}
        </Card>

        <Card className="min-w-[520px] grow-[1.6] basis-0 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-2.5 pt-3">
            <h2 className="text-[15px] font-bold leading-5 text-ink">Which model does which job</h2>
            {r ? (
              <div role="group" aria-label="Preset" className="inline-flex rounded-control bg-surface-2 p-0.5">
                {presets.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    aria-pressed={p.id === r.preset}
                    disabled={update.isPending}
                    onClick={() => p.id !== r.preset && update.mutate({ preset: p.id })}
                    className={cx("rounded-chip px-3 py-1 text-[13px] font-bold leading-4", p.id === r.preset ? "bg-action text-white" : "text-body hover:text-ink")}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          {routing.isPending ? (
            <LoadingState label="Loading model routing" className="border-t border-line py-10" />
          ) : routing.isError ? (
            <div className="border-t border-line p-4">
              <ErrorState title="Model routing could not be loaded" message={errorText(routing.error)} onRetry={() => routing.refetch()} />
            </div>
          ) : (
            <>
              <ul>
                {ROLES.map((x) => (
                  <RoleRow
                    key={x.role}
                    {...x}
                    route={r?.roles[x.role]}
                    connections={list}
                    models={modelsFor(r?.roles[x.role]?.provider ?? "")}
                    disabled={update.isPending}
                    onChange={(next) => setRole(x.role, next)}
                  />
                ))}
              </ul>
              <div className="flex flex-col gap-1 border-t border-line px-4 py-3 text-[13px] leading-[19px] text-body">
                <span>
                  {active
                    ? active.description || `${active.label} is on.`
                    : "Custom: you picked the models yourself. Choose a preset to go back to a recommended set."}
                </span>
                <span>Test a connection to see the models it offers; they then appear as suggestions when you type a model name.</span>
                <InlineError>{update.isError ? errorText(update.error) : null}</InlineError>
              </div>
            </>
          )}
        </Card>
      </div>
      {media.length ? (
        <Card className="overflow-hidden">
          <div className="flex items-baseline justify-between px-4 pb-2.5 pt-3.5">
            <h2 className="text-[15px] font-bold leading-5 text-ink">Media</h2>
            <span className="text-[12px] text-body">{media.filter((c) => statusOf(c).ok).length} of {media.length} ready · used to make pictures and video</span>
          </div>
          <ul>
            {media.map((c) => (
              <ConnectionRow key={c.id} c={c} onModels={() => {}} />
            ))}
          </ul>
        </Card>
      ) : null}
    </AppShell>
  );
}
