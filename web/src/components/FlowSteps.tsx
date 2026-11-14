import { Check } from "lucide-react";
import { Fragment } from "react";
import { cx } from "@/lib/format";

export const FLOW_STEPS = ["Say it", "Answer three questions", "Approve outline", "Watch it build", "Refine", "Review", "Ship"] as const;

/** The seven-step deck flow as a horizontal stepper (U04). `current` is 1-based. */
export function FlowSteps({ current }: { current: number }) {
  return (
    <ol className="flex shrink-0 items-center gap-3 overflow-x-auto border-b border-line px-10 py-3" aria-label="Deck steps">
      {FLOW_STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const here = n === current;
        return (
          <Fragment key={label}>
            {i > 0 ? <li aria-hidden className="h-px w-5 shrink-0 bg-line-strong" /> : null}
            <li className="flex shrink-0 items-center gap-2" aria-current={here ? "step" : undefined}>
              <span
                className={cx(
                  "flex size-5 items-center justify-center rounded-pill text-[11px] font-bold leading-none",
                  done ? "bg-pass-soft text-pass" : here ? "bg-action text-white" : "border border-line-strong text-body",
                )}
              >
                {done ? <Check size={12} strokeWidth={3} /> : n}
              </span>
              <span className={cx("whitespace-nowrap text-[13px] leading-4", here ? "font-bold text-ink" : "text-body")}>{label}</span>
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
