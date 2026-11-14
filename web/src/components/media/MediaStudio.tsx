"use client";

import { ProviderLogo } from "@/components/ProviderLogo";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Film, Image as ImageIcon, Play, Plus, RefreshCw, Sparkles, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { deckProblem } from "@/components/DeckStates";
import { AppShell } from "@/components/Shell";
import { Button, Card, Dropdown, EmptyState, ErrorState, InlineError, LoadingState, PageHeader, Pill, Segmented, Spinner } from "@/components/ui";
import { api, errorText, keys } from "@/lib/api";
import { useDeckEvents } from "@/lib/events";
import { cx } from "@/lib/format";
import { useDeck } from "@/lib/hooks";
import type { MediaAsset, MediaJob, MediaKind, MediaProvider } from "@/lib/types";

const ASPECTS = ["16:9", "4:3", "1:1", "3:4", "9:16"] as const;

function aspectStyle(a?: string | null): string {
  const [w, h] = (a ?? "16:9").split(":").map(Number);
  return w && h ? `${w} / ${h}` : "16 / 9";
}

/** Listens for media.updated on the deck stream (the shared hook does not know this event). */
function useMediaEvents(deckId: string) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!deckId || typeof EventSource === "undefined") return;
    const source = new EventSource(api.eventsUrl(deckId));
    source.addEventListener("media.updated", () => {
      qc.invalidateQueries({ queryKey: keys.mediaJobs(deckId) });
      qc.invalidateQueries({ queryKey: keys.media(deckId) });
    });
    return () => source.close();
  }, [deckId, qc]);
}

function ProviderTile({ p, on, onToggle }: { p: MediaProvider; on: boolean; onToggle: () => void }) {
  const usable = p.connected || p.id === "offline";
  if (!usable) {
    return (
      <div className="flex min-h-10 items-center justify-between gap-2 rounded-control border py-2 border-line px-3 text-[13px] text-muted" title={p.detail ?? undefined}>
        <span className="flex min-w-0 items-center gap-2"><ProviderLogo id={p.id} label={p.label} size={20} /><span className="min-w-0 break-words leading-[16px]">{p.label}</span></span>
        <Link href="/connections" className="shrink-0 text-[12px] font-bold text-action hover:underline">
          Connect
        </Link>
      </div>
    );
  }
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onToggle}
      title={[p.detail, p.cost_hint].filter(Boolean).join(" · ") || undefined}
      className={cx(
        "flex min-h-10 items-center justify-between gap-2 rounded-control border py-2 px-3 text-left text-[13px] font-bold text-ink",
        on ? "border-action bg-action-soft" : "border-line-strong hover:bg-surface",
      )}
    >
      <span className="flex min-w-0 items-center gap-2"><ProviderLogo id={p.id} label={p.label} size={20} /><span className="min-w-0 break-words leading-[16px]">{p.label}</span></span>
      {on ? <Check size={15} className="shrink-0 text-action" aria-hidden /> : null}
    </button>
  );
}

function AssetTile({ a, n, selected, onSelect }: { a: MediaAsset; n: number; selected: boolean; onSelect: () => void }) {
  const src = api.mediaUrl(a.url);
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={cx(
          "relative overflow-hidden rounded-control border bg-surface",
          selected ? "border-action shadow-[0_0_0_2px_var(--action)]" : "border-line hover:border-line-strong",
        )}
        style={{ aspectRatio: aspectStyle(a.aspect ?? `${a.width}:${a.height}`) }}
      >
        {a.kind === "video" ? (
          <>
            <video src={src} poster={a.poster_url ? api.mediaUrl(a.poster_url) : undefined} muted loop playsInline preload="metadata" className="size-full object-cover" onMouseEnter={(e) => e.currentTarget.play().catch(() => {})} onMouseLeave={(e) => e.currentTarget.pause()} />
            <span className="absolute left-1/2 top-1/2 flex size-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-pill bg-ink text-white">
              <Play size={15} aria-hidden />
            </span>
          </>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={a.prompt} className="size-full object-cover" />
        )}
        {selected ? (
          <span className="absolute right-2 top-2 flex size-5 items-center justify-center rounded-pill bg-action text-white">
            <Check size={13} aria-hidden />
          </span>
        ) : null}
      </button>
      <div className="flex justify-between gap-2 text-[12px] leading-4">
        <span className={cx("truncate font-bold", selected ? "text-action" : "text-ink")}>
          {n} · {a.provider}
        </span>
        {a.cost_estimate != null ? <span className="shrink-0 text-body">
            {a.provider === "higgsfield" ? `${a.cost_estimate} credits` : `$${a.cost_estimate.toFixed(2)}`}
          </span> : null}
      </div>
    </div>
  );
}

function jobLine(j: MediaJob): string {
  const who = j.providers.join(", ");
  if (j.status === "pending") return `Waiting to start (${who})`;
  if (j.status === "running") return `Making ${j.kind === "video" ? "a video" : "pictures"} with ${who}`;
  if (j.status === "failed") return j.errors[0]?.detail || "It did not work.";
  return `${j.asset_ids.length} ${j.kind === "video" ? "video" : "picture"}${j.asset_ids.length === 1 ? "" : "s"} ready`;
}

export function MediaStudio({ deckId, slideId }: { deckId: string; slideId: string | null }) {
  const router = useRouter();
  const qc = useQueryClient();
  const deck = useDeck(deckId);
  useDeckEvents(deckId);
  useMediaEvents(deckId);

  const slides = useMemo(() => deck.data?.slides ?? [], [deck.data]);
  const [pickedSlide, setPickedSlide] = useState<string | null>(slideId);
  const slide = slides.find((s) => s.id === pickedSlide);
  const slideN = slide ? slide.index : null;

  const providers = useQuery({ queryKey: keys.mediaProviders, queryFn: api.listMediaProviders, retry: false });
  const suggest = useQuery({
    queryKey: keys.mediaSuggest(deckId, pickedSlide ?? ""),
    queryFn: () => api.suggestMedia(deckId, pickedSlide ?? undefined),
    retry: false,
    staleTime: Infinity,
  });
  const jobs = useQuery({
    queryKey: keys.mediaJobs(deckId),
    queryFn: () => api.listMediaJobs(deckId),
    retry: false,
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "pending" || j.status === "running") ? 2_000 : false),
  });
  const anyPending = jobs.data?.some((j) => j.status === "pending" || j.status === "running") ?? false;
  const assets = useQuery({
    queryKey: keys.media(deckId),
    queryFn: () => api.listMedia(deckId),
    retry: false,
    refetchInterval: anyPending ? 3_000 : false,
  });

  const [kind, setKind] = useState<MediaKind>("image");
  const [aspect, setAspect] = useState<string>("16:9");
  const [prompt, setPrompt] = useState<{ text: string; from: string } | null>(null);
  const suggestionKey = pickedSlide ?? "";
  const promptText = prompt && prompt.from === suggestionKey ? prompt.text : (suggest.data?.prompt ?? "");
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const list = providers.data ?? [];
  const forKind = list.filter((p) => p.kinds.includes(kind) && p.id !== "upload");
  const usable = (p: MediaProvider) => p.connected || p.id === "offline";
  const defaults = forKind.filter((p) => usable(p) && p.is_default).map((p) => p.id);
  const active = (chosen ?? (defaults.length ? defaults : forKind.filter((p) => p.id === "offline").map((p) => p.id))).filter((id) =>
    forKind.some((p) => p.id === id && usable(p)),
  );
  const toggle = (id: string) => setChosen(active.includes(id) ? active.filter((x) => x !== id) : [...active, id]);

  const invalidateMedia = () => {
    qc.invalidateQueries({ queryKey: keys.mediaJobs(deckId) });
    qc.invalidateQueries({ queryKey: keys.media(deckId) });
  };
  const generate = useMutation({
    mutationFn: () =>
      api.generateMedia(deckId, {
        slide_id: pickedSlide ?? undefined,
        prompt: promptText.trim(),
        kind,
        aspect,
        providers: active,
        style: suggest.data?.style,
      }),
    onSuccess: invalidateMedia,
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadMedia(deckId, file, pickedSlide ?? undefined),
    onSuccess: (a) => {
      setSelected(a.id);
      invalidateMedia();
    },
  });
  const place = useMutation({
    mutationFn: () => api.placeMedia(deckId, pickedSlide!, selected!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.deck(deckId) });
      qc.invalidateQueries({ queryKey: keys.render(deckId) });
      router.push(`/decks/${deckId}?slide=${pickedSlide}`);
    },
  });

  const shown = (assets.data ?? []).filter((a) => !pickedSlide || !a.slide_id || a.slide_id === pickedSlide);
  const latest = jobs.data?.[0];
  const selectedAsset = shown.find((a) => a.id === selected);
  const problem = deckProblem(deck, false);
  const title = deck.data?.title || "Deck";

  return (
    <AppShell
      crumbs={[{ label: "Home", href: "/" }, { label: title, href: `/decks/${deckId}${pickedSlide ? `?slide=${pickedSlide}` : ""}` }, { label: "Media" }]}
    >
      {problem ?? (
        <>
          <PageHeader
            icon={<ImageIcon size={22} />}
            title={slideN ? `Make a picture for slide ${slideN}` : "Make a picture"}
            subtitle="Say what it should show, pick who makes it, then choose the one that fits."
            actions={
              latest?.status === "done" ? <Pill tone="pass"><Check size={13} aria-hidden /> {jobLine(latest)}</Pill> : null
            }
          />

          <div className="flex flex-wrap items-start gap-4">
            {/* Left: prompt and settings */}
            <Card className="flex w-full min-w-[300px] flex-col gap-4 p-4 lg:w-[320px] lg:grow-0">
              <h2 className="text-[16px] font-bold leading-5 text-ink">What should it show</h2>
              <div className="flex flex-col gap-1">
                <span className="text-[12px] text-body">Slide</span>
                <Dropdown
                  ariaLabel="Slide"
                  value={pickedSlide ?? ""}
                  onChange={(v) => setPickedSlide(v || null)}
                  options={[{ value: "", label: "No slide, just the library" }, ...slides.map((s) => ({ value: s.id, label: `${s.index}. ${s.headline || "Untitled"}` }))]}
                />
              </div>
              <div className="overflow-hidden rounded-control border border-line-strong focus-within:border-action">
                <textarea
                  value={promptText}
                  onChange={(e) => setPrompt({ text: e.target.value, from: suggestionKey })}
                  rows={5}
                  aria-label="What the picture should show"
                  placeholder={suggest.isPending ? "Writing a suggestion" : "Describe the picture"}
                  className="block w-full resize-none bg-bg px-3 py-2.5 text-[14px] leading-5 text-ink placeholder:text-muted"
                />
                {slide || suggest.data?.headline ? (
                  <div className="border-t border-line bg-surface px-3 py-2 text-[12px] leading-4 text-body">
                    Using slide {slideN ?? (suggest.data?.slide_index != null ? suggest.data.slide_index : "")}: &ldquo;{slide?.headline ?? suggest.data?.headline}&rdquo;
                  </div>
                ) : null}
              </div>
              {suggest.isError ? <p className="text-[12px] text-body">No suggestion this time. Write what you want to see.</p> : null}

              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] text-body">Type</span>
                <Segmented
                  label="Type"
                  value={kind}
                  onChange={(k) => {
                    setKind(k);
                    setChosen(null);
                  }}
                  options={[{ value: "image", label: "Image" }, { value: "video", label: "Video" }]}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <div className="flex justify-between text-[12px]">
                  <span className="text-body">Made by · {active.length} picked</span>
                  <Link href="/connections" className="font-bold text-action hover:underline">Manage</Link>
                </div>
                {providers.isPending ? (
                  <Spinner />
                ) : providers.isError ? (
                  <InlineError>Picture makers could not be loaded. {errorText(providers.error)}</InlineError>
                ) : forKind.length === 0 ? (
                  <p className="text-[13px] text-body">Nothing can make a {kind} yet.</p>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {forKind.map((p) => (
                      <ProviderTile key={p.id} p={p} on={active.includes(p.id)} onToggle={() => toggle(p.id)} />
                    ))}
                  </div>
                )}
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*,video/*"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) upload.mutate(f);
                    e.target.value = "";
                  }}
                />
                <Button className="mt-1 w-full border-dashed" busy={upload.isPending} onClick={() => fileRef.current?.click()}>
                  <Upload size={15} /> Upload your own
                </Button>
                <InlineError>{upload.isError ? errorText(upload.error) : null}</InlineError>
              </div>

              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] text-body">Shape</span>
                <div className="grid grid-cols-5 gap-1.5" role="group" aria-label="Shape">
                  {ASPECTS.map((a) => (
                    <button
                      key={a}
                      type="button"
                      aria-pressed={a === aspect}
                      onClick={() => setAspect(a)}
                      className={cx(
                        "h-8 rounded-control border text-[13px] font-bold",
                        a === aspect ? "border-action bg-action-soft text-action" : "border-line-strong text-ink hover:bg-surface",
                      )}
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </div>

              <Button
                variant="primary"
                size="lg"
                busy={generate.isPending}
                disabled={!promptText.trim() || active.length === 0}
                onClick={() => generate.mutate()}
              >
                <Sparkles size={16} /> Generate
              </Button>
              <InlineError>{generate.isError ? errorText(generate.error) : null}</InlineError>
            </Card>

            {/* Middle: results */}
            <Card className="flex min-w-[340px] grow basis-0 flex-col gap-3 p-4">
              <div className="flex items-baseline justify-between gap-2">
                <h2 className="text-[16px] font-bold leading-5 text-ink">
                  Results <span className="text-[13px] font-normal text-body">Pick one</span>
                </h2>
                {latest ? (
                  <span role="status" className={cx("flex items-center gap-1.5 text-[12px]", latest.status === "failed" ? "text-fail" : "text-body")}>
                    {latest.status === "pending" || latest.status === "running" ? <Spinner size={13} /> : null}
                    {jobLine(latest)}
                  </span>
                ) : null}
              </div>
              {latest && latest.status !== "failed" && latest.errors.length ? (
                <ul className="flex flex-col gap-0.5 text-[12px] text-fail">
                  {latest.errors.map((e) => (
                    <li key={e.provider}>{e.provider}: {e.detail}</li>
                  ))}
                </ul>
              ) : null}
              {assets.isPending ? (
                <LoadingState label="Loading pictures" />
              ) : assets.isError ? (
                <ErrorState title="Pictures could not be loaded" message={errorText(assets.error)} onRetry={() => assets.refetch()} />
              ) : shown.length === 0 ? (
                <EmptyState
                  icon={kind === "video" ? <Film size={20} /> : <ImageIcon size={20} />}
                  title={anyPending ? "Making them now" : "Nothing here yet"}
                  message={anyPending ? "They appear here as each one is ready." : "Press Generate, or upload a picture of your own."}
                />
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                  {shown.map((a, i) => (
                    <AssetTile key={a.id} a={a} n={i + 1} selected={a.id === selected} onSelect={() => setSelected(a.id === selected ? null : a.id)} />
                  ))}
                </div>
              )}
            </Card>

            {/* Right: place */}
            <div className="flex w-full min-w-[280px] flex-col gap-3 lg:w-[300px] lg:grow-0">
              <Card className="flex flex-col gap-2 p-4 text-[13px] leading-[19px]">
                <h2 className="text-[16px] font-bold leading-5 text-ink">{slideN ? `Goes on slide ${slideN}` : "Choose a slide"}</h2>
                {selectedAsset ? (
                  <dl className="flex flex-col">
                    <div className="flex justify-between border-t border-line py-2"><dt className="text-body">Made by</dt><dd className="font-bold text-ink">{selectedAsset.provider}</dd></div>
                    <div className="flex justify-between border-t border-line py-2"><dt className="text-body">Size</dt><dd className="font-bold text-ink">{selectedAsset.width} × {selectedAsset.height}{selectedAsset.aspect ? `, ${selectedAsset.aspect}` : ""}</dd></div>
                  </dl>
                ) : (
                  <p className="text-body">Pick a result to put it on the slide.</p>
                )}
                {!pickedSlide ? <p className="text-body">Choose a slide on the left to place it.</p> : null}
              </Card>
              <Button size="lg" busy={generate.isPending} disabled={!promptText.trim() || active.length === 0} onClick={() => generate.mutate()}>
                <RefreshCw size={16} /> Generate again
              </Button>
              <Button variant="primary" size="lg" busy={place.isPending} disabled={!selected || !pickedSlide} onClick={() => place.mutate()}>
                <Plus size={16} /> {slideN ? `Use on slide ${slideN}` : "Use on slide"}
              </Button>
              <InlineError>{place.isError ? errorText(place.error) : null}</InlineError>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
