"use client";

import Link from "next/link";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/format";
import { Dropdown } from "./Dropdown";

export { Dropdown, Combobox, type DropdownOption } from "./Dropdown";

/* ---------- Buttons ---------- */

type Variant = "primary" | "secondary" | "ghost" | "ink";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "border border-line-strong bg-bg text-ink hover:bg-surface",
  ghost: "text-ink hover:bg-surface-2",
  ink: "bg-ink text-white hover:opacity-90",
};
const SIZES: Record<Size, string> = {
  sm: "h-[30px] px-3 text-[13px] leading-4 gap-1.5",
  md: "h-9 px-3.5 text-[14px] leading-4 gap-2",
  lg: "h-11 px-5 text-[15px] leading-5 gap-2",
};

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra?: string) {
  return cx(
    "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-control font-bold transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-50",
    VARIANTS[variant],
    SIZES[size],
    extra,
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
};

export function Button({ variant, size, busy, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button type="button" className={buttonClass(variant, size, className)} disabled={disabled || busy} {...rest}>
      {busy ? <Loader2 size={16} className="spin" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function LinkButton({
  href, variant, size, className, children,
}: { href: string; variant?: Variant; size?: Size; className?: string; children: ReactNode }) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

/* ---------- Pills, cards ---------- */

export type Tone = "neutral" | "pass" | "fail" | "warn" | "ai" | "teal" | "action";
const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-body",
  pass: "bg-pass-soft text-pass",
  fail: "bg-fail-soft text-fail",
  warn: "bg-warn-soft text-warn",
  ai: "bg-ai-soft text-ai-ink",
  teal: "bg-teal-soft text-teal",
  action: "bg-action-soft text-action",
};

export function Pill({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-pill px-2 py-0.5 text-[12px] font-bold leading-4",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-card border border-line bg-bg", className)}>{children}</div>;
}

/** Agent output and proposals. */
export function AiCard({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-card border border-ai-line bg-ai-soft", className)}>{children}</div>;
}

export function PageHeader({
  icon, title, subtitle, actions,
}: { icon?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex w-full shrink-0 flex-wrap items-center gap-4">
      {icon ? (
        <div className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-action-soft text-action">
          {icon}
        </div>
      ) : null}
      <div className="flex min-w-0 grow basis-0 flex-col gap-0.5">
        <h1 className="text-[28px] font-bold leading-8 text-ink">{title}</h1>
        {subtitle ? <p className="text-[15px] leading-5 text-body">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/* ---------- States ---------- */

export function Spinner({ size = 18 }: { size?: number }) {
  return <Loader2 size={size} className="spin text-muted" aria-hidden />;
}

export function LoadingState({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cx("flex items-center justify-center gap-2.5 py-16 text-[14px] text-body", className)}>
      <Spinner />
      {label}
    </div>
  );
}

export function ErrorState({
  title = "That did not work", message, onRetry, children, className,
}: { title?: string; message: string; onRetry?: () => void; children?: ReactNode; className?: string }) {
  return (
    <div role="alert" className={cx("flex items-start gap-3 rounded-card border border-line bg-bg p-4", className)}>
      <div className="flex size-7 shrink-0 items-center justify-center rounded-pill bg-fail-soft text-fail">
        <AlertTriangle size={15} aria-hidden />
      </div>
      <div className="flex min-w-0 grow flex-col gap-1">
        <div className="text-[15px] font-bold leading-5 text-ink">{title}</div>
        <div className="text-[13px] leading-[19px] text-body">{message}</div>
        {onRetry || children ? (
          <div className="flex items-center gap-2 pt-2">
            {onRetry ? (
              <Button size="sm" onClick={onRetry}>
                Try again
              </Button>
            ) : null}
            {children}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function EmptyState({
  icon, title, message, children, className,
}: { icon?: ReactNode; title: string; message?: string; children?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex flex-col items-center gap-2 rounded-card border border-dashed border-line-strong px-6 py-12 text-center", className)}>
      {icon ? (
        <div className="mb-1 flex size-11 items-center justify-center rounded-card bg-action-soft text-action">{icon}</div>
      ) : null}
      <div className="text-[17px] font-bold leading-6 text-ink">{title}</div>
      {message ? <div className="max-w-[440px] text-[14px] leading-5 text-body">{message}</div> : null}
      {children ? <div className="flex items-center gap-2 pt-3">{children}</div> : null}
    </div>
  );
}

/** A short inline error under a control. */
export function InlineError({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-[13px] leading-[18px] text-fail">
      {children}
    </p>
  );
}

/* ---------- Controls ---------- */

export function Toggle({
  checked, onChange, label, disabled,
}: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-[14px] font-bold text-ink disabled:opacity-50"
    >
      <span
        className={cx(
          "flex h-5 w-9 shrink-0 items-center rounded-pill p-0.5 transition-colors",
          checked ? "justify-end bg-action" : "justify-start bg-line-strong",
        )}
      >
        <span className="size-4 rounded-pill bg-white" />
      </span>
      {label}
    </button>
  );
}

export function Segmented<T extends string>({
  value, options, onChange, label,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-control bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-chip px-2.5 py-1 text-[13px] font-bold leading-4",
            o.value === value ? "bg-bg text-ink shadow-[0_0_0_1px_var(--line)]" : "text-body hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ProgressBar({ value, tone = "action" }: { value: number; tone?: "ink" | "action" | "pass" }) {
  const pct = Math.max(0, Math.min(100, value));
  // Progress uses the blue accent; "ink" stays for callers that want a neutral dark bar.
  const fill = tone === "action" ? "bg-[image:var(--action-gradient)]" : tone === "pass" ? "bg-pass" : "bg-ink";
  return (
    <div className="h-1 w-full overflow-hidden rounded-pill bg-surface-2" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-1 rounded-pill", fill)} style={{ width: `${pct}%` }} />
    </div>
  );
}

/** A custom dropdown dressed as a chip: optional icon, quiet label, bold value. */
export function SelectChip({
  icon, label, value, onChange, options, ariaLabel, className,
}: {
  icon?: ReactNode;
  label?: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  ariaLabel?: string;
  className?: string;
}) {
  const current = options.find((o) => o.value === value);
  return (
    <Dropdown
      value={value}
      options={options}
      onChange={onChange}
      ariaLabel={ariaLabel ?? label ?? "Choose"}
      className={cx("shrink-0", className)}
      minMenuWidth={200}
    >
      {icon ? <span className="flex shrink-0 text-body">{icon}</span> : null}
      {label ? <span className="shrink-0 text-body">{label}</span> : null}
      <span className="truncate font-bold text-ink">{current?.label ?? "Choose"}</span>
    </Dropdown>
  );
}
