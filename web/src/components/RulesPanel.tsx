"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Shield, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, errorText, keys } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Button, Card, ErrorState, InlineError, LoadingState } from "./ui";

/** The standing rules every agent follows on every deck: list, add, delete. */
export function RulesPanel({ className }: { className?: string }) {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: keys.rules, queryFn: api.listRules });
  const [text, setText] = useState("");
  const done = () => qc.invalidateQueries({ queryKey: keys.rules });
  const add = useMutation({
    mutationFn: (value: string) => api.addRule(value),
    onSuccess: () => {
      setText("");
      done();
    },
  });
  const remove = useMutation({ mutationFn: (rid: string) => api.deleteRule(rid), onSuccess: done });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (text.trim() && !add.isPending) add.mutate(text.trim());
  }

  return (
    <Card className={className}>
      <div className="flex flex-col gap-0.5 px-4 pb-3 pt-3.5">
        <h2 className="text-[15px] font-bold leading-5 text-ink">Your rules</h2>
        <p className="text-[13px] leading-[19px] text-body">Say it once. Every agent follows it on every deck.</p>
      </div>

      {rules.isPending ? (
        <LoadingState label="Loading your rules" className="border-t border-line py-8" />
      ) : rules.isError ? (
        <div className="border-t border-line p-4">
          <ErrorState title="Your rules could not be loaded" message={errorText(rules.error)} onRetry={() => rules.refetch()} />
        </div>
      ) : rules.data.length === 0 ? (
        <p className="border-t border-line px-4 py-4 text-[13px] leading-[19px] text-body">
          No rules yet. Add one below, for example “Never use the word synergy” or “Always show currency in USD”.
        </p>
      ) : (
        <ul>
          {rules.data.map((r) => (
            <li key={r.id} className="flex items-start gap-3 border-t border-line px-4 py-3">
              <Shield size={16} className="mt-0.5 shrink-0 text-body" aria-hidden />
              <div className="flex min-w-0 grow flex-col gap-0.5">
                <span className="text-[14px] font-bold leading-[18px] text-ink">{r.text}</span>
                <span className="text-[12px] leading-4 text-body">
                  Set {timeAgo(r.created_at)}
                  {r.source ? ` · ${r.source}` : ""}
                </span>
              </div>
              <button
                type="button"
                aria-label={`Delete the rule: ${r.text}`}
                title="Delete this rule"
                disabled={remove.isPending}
                onClick={() => remove.mutate(r.id)}
                className="flex size-7 shrink-0 items-center justify-center rounded-chip text-body hover:bg-surface-2 hover:text-fail disabled:opacity-40"
              >
                <Trash2 size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={submit} className="flex flex-col gap-2 border-t border-line p-4">
        <div className="flex h-10 items-center gap-2 rounded-control border border-line-strong pl-3 pr-1.5 focus-within:border-action">
          <Plus size={16} className="shrink-0 text-body" aria-hidden />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Add a rule"
            placeholder="Add a rule, in your own words"
            className="min-w-0 grow bg-transparent text-[14px] text-ink placeholder:text-muted"
          />
          <Button type="submit" size="sm" variant="ghost" disabled={!text.trim()} busy={add.isPending}>
            Add
          </Button>
        </div>
        <InlineError>{add.isError ? errorText(add.error) : remove.isError ? errorText(remove.error) : null}</InlineError>
        <p className="text-[12px] leading-[17px] text-body">
          Choosing “Keep it, this is intentional” on a Critic finding also adds a rule here, so the Critic stops raising it.
        </p>
      </form>
    </Card>
  );
}
