"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ArrowUpRight, GalleryHorizontalEnd, MessageSquare, Palette, Users } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { AppShell, StepChip } from "@/components/Shell";
import { Button, InlineError, SelectChip } from "@/components/ui";
import { AttachTools, SourceChip } from "@/components/sources/SourceParts";
import { api, errorText, keys } from "@/lib/api";
import { AUDIENCES, EXAMPLES, LENGTHS, STARTERS, TONES } from "@/lib/starters";
import type { DataSource } from "@/lib/types";

function Composer() {
  const router = useRouter();
  const qc = useQueryClient();
  const start = useSearchParams().get("start");
  const starter = STARTERS.find((s) => s.key === start);
  const [prompt, setPrompt] = useState(starter?.prompt ?? "");
  const [audience, setAudience] = useState(AUDIENCES[0]);
  const [length, setLength] = useState("10");
  const [tone, setTone] = useState(TONES[0]);
  const [brandKit, setBrandKit] = useState("none");
  const [sources, setSources] = useState<DataSource[]>([]);
  const brandKits = useQuery({ queryKey: keys.brandKits, queryFn: api.listBrandKits });
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const create = useMutation({
    mutationFn: async () => {
      const deck = await api.createDeck({ prompt: prompt.trim(), audience, tone, slide_count: Number(length), interview: true, source_ids: sources.length ? sources.map((s) => s.id) : undefined });
      if (brandKit !== "none") await api.setDeckBrandKit(deck.id, brandKit);
      return deck;
    },
    onSuccess: (deck) => {
      qc.setQueryData(keys.deck(deck.id), deck);
      qc.invalidateQueries({ queryKey: keys.decks });
      router.push(`/decks/${deck.id}/interview`);
    },
  });

  const ready = prompt.trim().length >= 8;
  const submit = () => {
    if (ready && !create.isPending) create.mutate();
  };

  return (
    <>
      <h1 className="pt-2 text-[56px] font-bold leading-[60px] tracking-[-0.02em] text-ink">What do you need to say?</h1>

      <div className="flex flex-col gap-3">
        <div className="flex flex-col rounded-card border border-line-strong bg-bg focus-within:border-action">
          <textarea
            ref={box}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
            }}
            rows={5}
            aria-label="What the deck should say"
            placeholder="Say it the way you would to a colleague. Who is it for, what should they decide, and which numbers matter?"
            className="min-h-[168px] resize-y bg-transparent px-5 pb-3 pt-5 text-[20px] leading-[30px] text-ink placeholder:text-muted"
          />
          {sources.length ? (
            <div className="flex flex-wrap gap-2 px-5 pb-3" aria-label="Attached data sources">
              {sources.map((s) => (
                <SourceChip
                  key={s.id}
                  source={s}
                  onRemove={() => {
                    setSources((all) => all.filter((x) => x.id !== s.id));
                    void api.deleteSource(s.id).catch(() => undefined);
                  }}
                />
              ))}
            </div>
          ) : null}
          <AttachTools className="border-t border-line px-3 py-2" onAdded={(s) => setSources((all) => [...all, s])} />
          <div className="flex items-center justify-between gap-3 border-t border-line py-2.5 pl-5 pr-2.5">
            <span className="text-[13px] leading-4 text-body">
              {starter ? `Started from “${starter.title}”. ` : ""}Next, the Strategist asks three short questions, then drafts an outline for you to approve. Nothing is designed yet.
            </span>
            <Button variant="primary" size="lg" onClick={submit} disabled={!ready} busy={create.isPending}>
              Build outline <ArrowRight size={18} />
            </Button>
          </div>
        </div>
        <InlineError>{create.isError ? errorText(create.error) : null}</InlineError>

        <div className="flex flex-wrap items-center gap-2">
          <SelectChip icon={<Users size={16} />} label="Audience" value={audience} onChange={setAudience} options={AUDIENCES.map((a) => ({ value: a, label: a }))} />
          <SelectChip
            icon={<GalleryHorizontalEnd size={16} />}
            label="Length"
            value={length}
            onChange={setLength}
            options={LENGTHS.map((n) => ({ value: String(n), label: `About ${n} slides` }))}
          />
          <SelectChip icon={<MessageSquare size={16} />} label="Tone" value={tone} onChange={setTone} options={TONES.map((t) => ({ value: t, label: t }))} />
          {brandKits.data && brandKits.data.length > 0 ? (
            <SelectChip
              icon={<Palette size={16} />}
              label="Brand"
              value={brandKit}
              onChange={setBrandKit}
              options={[{ value: "none", label: "Lectern default" }, ...brandKits.data.map((k) => ({ value: k.id, label: k.name }))]}
            />
          ) : null}
        </div>
      </div>

      <section className="flex flex-col gap-2.5 pt-6" aria-label="Examples">
        <div className="label">New here? Try an example</div>
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.title}
              type="button"
              onClick={() => {
                setPrompt(ex.prompt);
                box.current?.focus();
              }}
              className="flex flex-col gap-1.5 rounded-card border border-line bg-bg p-4 text-left hover:border-line-strong hover:bg-surface"
            >
              <span className="flex items-center justify-between text-[15px] font-bold leading-5 text-ink">
                {ex.title} <ArrowUpRight size={18} className="text-body" aria-hidden />
              </span>
              <span className="text-[14px] leading-5 text-body">{ex.prompt}</span>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

export default function NewDeckPage() {
  return (
    <AppShell crumbs={[{ label: "Home", href: "/" }, { label: "New deck" }]} chip={<StepChip step={1} />}>
      <Suspense fallback={null}>
        <Composer />
      </Suspense>
    </AppShell>
  );
}
