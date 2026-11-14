"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cx } from "@/lib/format";

export type DropdownOption = { value: string; label: string; hint?: string; disabled?: boolean; icon?: ReactNode };

/** Fixed-position popover anchored under (or above, if no room) a trigger. */
function usePopover(open: boolean, anchor: React.RefObject<HTMLElement | null>, minWidth?: number) {
  const [pos, setPos] = useState<{ left?: number; right?: number; top: number; width: number; maxHeight: number; up: boolean } | null>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = anchor.current?.getBoundingClientRect();
      if (!r) return;
      const below = window.innerHeight - r.bottom - 12;
      const above = r.top - 12;
      const up = below < 200 && above > below;
      const width = Math.max(r.width, minWidth ?? 0);
      // Near the right edge the menu (up to 360px wide) lines up with the trigger's right edge instead of
      // sliding left past it.
      const alignRight = r.left + Math.max(width, 360) > window.innerWidth - 8;
      const side = alignRight ? { right: Math.max(8, window.innerWidth - r.right) } : { left: Math.max(8, r.left) };
      setPos({ ...side, top: up ? r.top - 6 : r.bottom + 6, width, maxHeight: Math.min(320, up ? above : below), up });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor, minWidth]);
  return pos;
}

function useOutside(open: boolean, refs: React.RefObject<HTMLElement | null>[], close: () => void) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (refs.some((r) => r.current?.contains(e.target as Node))) return;
      close();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, refs, close]);
}

function Menu({
  id, pos, options, value, active, onPick, onHover, listRef,
}: {
  id: string;
  pos: NonNullable<ReturnType<typeof usePopover>>;
  options: DropdownOption[];
  value: string;
  active: number;
  onPick: (o: DropdownOption) => void;
  onHover: (i: number) => void;
  listRef: React.RefObject<HTMLUListElement | null>;
}) {
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, listRef]);
  return createPortal(
    <ul
      ref={listRef}
      id={id}
      role="listbox"
      className="dropdown-menu scroll-thin fixed z-50 overflow-y-auto rounded-control border border-line bg-bg p-1"
      style={{
        left: pos.left,
        right: pos.right,
        top: pos.up ? undefined : pos.top,
        bottom: pos.up ? window.innerHeight - pos.top : undefined,
        minWidth: pos.width,
        maxWidth: Math.max(pos.width, 360),
        maxHeight: pos.maxHeight,
      }}
    >
      {options.length === 0 ? <li className="px-2.5 py-2 text-[13px] text-body">No matches</li> : null}
      {options.map((o, i) => {
        const selected = o.value === value;
        return (
          <li
            key={o.value}
            data-index={i}
            role="option"
            aria-selected={selected}
            aria-disabled={o.disabled || undefined}
            onMouseDown={(e) => e.preventDefault()}
            onMouseEnter={() => onHover(i)}
            onClick={() => !o.disabled && onPick(o)}
            className={cx(
              "flex cursor-pointer items-center gap-2 rounded-chip px-2.5 py-2 text-[14px] leading-[18px]",
              i === active && !o.disabled && "bg-surface-2",
              selected ? "font-bold text-action" : "text-ink",
              o.disabled && "cursor-not-allowed opacity-50",
            )}
          >
            {o.icon ? <span className="flex shrink-0">{o.icon}</span> : null}
            <span className="min-w-0 grow truncate">{o.label}</span>
            {o.hint ? <span className="shrink-0 pl-3 text-[12px] font-normal text-body">{o.hint}</span> : null}
            <span className="flex w-4 shrink-0 justify-end">{selected ? <Check size={15} aria-hidden /> : null}</span>
          </li>
        );
      })}
    </ul>,
    document.body,
  );
}

function nextEnabled(options: DropdownOption[], from: number, step: number) {
  for (let i = 1; i <= options.length; i++) {
    const j = (from + step * i + options.length) % options.length;
    if (!options[j].disabled) return j;
  }
  return from;
}

/** Custom select: button trigger + listbox popover. Keyboard: arrows, Home/End, Enter/Space, Esc, type-ahead. */
export function Dropdown({
  value, options, onChange, ariaLabel, disabled, className, triggerClassName, children, minMenuWidth,
}: {
  value: string;
  options: DropdownOption[];
  onChange: (v: string) => void;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Custom trigger content; defaults to the selected label. */
  children?: ReactNode;
  minMenuWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const pos = usePopover(open, trigger, minMenuWidth);
  const typed = useRef({ text: "", at: 0 });
  const current = options.find((o) => o.value === value);

  const close = () => setOpen(false);
  useOutside(open, [trigger, list], close);

  const show = () => {
    if (disabled) return;
    const i = options.findIndex((o) => o.value === value);
    setActive(i >= 0 ? i : nextEnabled(options, -1, 1));
    setOpen(true);
  };
  const pick = (o: DropdownOption) => {
    onChange(o.value);
    setOpen(false);
    trigger.current?.focus();
  };

  const onKey = (e: KeyboardEvent) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        show();
      }
      return;
    }
    if (e.key === "Escape" || e.key === "Tab") return close();
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => nextEnabled(options, a, 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => nextEnabled(options, a, -1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(nextEnabled(options, -1, 1)); }
    else if (e.key === "End") { e.preventDefault(); setActive(nextEnabled(options, options.length, -1)); }
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const o = options[active];
      if (o && !o.disabled) pick(o);
    } else if (e.key.length === 1) {
      const now = Date.now();
      typed.current = { text: (now - typed.current.at < 600 ? typed.current.text : "") + e.key.toLowerCase(), at: now };
      const j = options.findIndex((o) => !o.disabled && o.label.toLowerCase().startsWith(typed.current.text));
      if (j >= 0) setActive(j);
    }
  };

  return (
    <div className={cx("relative inline-flex", className)}>
      <button
        ref={trigger}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        disabled={disabled}
        onClick={() => (open ? close() : show())}
        onKeyDown={onKey}
        className={cx(
          "inline-flex h-9 w-full items-center gap-2 rounded-control border bg-bg pl-3 pr-2.5 text-left text-[14px] leading-4 transition-colors",
          "hover:bg-surface disabled:cursor-not-allowed disabled:opacity-60",
          open ? "border-action ring-2 ring-action-soft" : "border-line-strong",
          triggerClassName,
        )}
      >
        <span className="flex min-w-0 grow items-center gap-2">
          {children ?? <span className="truncate font-bold text-ink">{current?.label ?? "Choose"}</span>}
        </span>
        <ChevronDown size={15} aria-hidden className={cx("shrink-0 text-body transition-transform", open && "rotate-180")} />
      </button>
      {open && pos ? (
        <Menu id={id} pos={pos} options={options} value={value} active={active} onPick={pick} onHover={setActive} listRef={list} />
      ) : null}
    </div>
  );
}

/** Free-text input with a custom suggestion list (replaces native datalist). */
export function Combobox({
  value, onChange, onCommit, suggestions, ariaLabel, placeholder, disabled, className,
}: {
  value: string;
  onChange: (v: string) => void;
  onCommit: () => void;
  suggestions: string[];
  ariaLabel: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  const pos = usePopover(open, input);
  const q = value.trim().toLowerCase();
  const options: DropdownOption[] = suggestions
    .filter((s) => !q || s.toLowerCase().includes(q) || suggestions.includes(value))
    .map((s) => ({ value: s, label: s }));

  const close = () => setOpen(false);
  useOutside(open, [input, list], close);

  const pick = (o: DropdownOption) => {
    onChange(o.value);
    setOpen(false);
    requestAnimationFrame(() => input.current?.blur());
  };

  return (
    <div className={cx("relative inline-flex", className)}>
      <input
        ref={input}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-autocomplete="list"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onFocus={() => suggestions.length && setOpen(true)}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(-1); }}
        onBlur={() => { setOpen(false); onCommit(); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Escape") close();
          else if (e.key === "Enter") {
            if (open && active >= 0 && options[active]) { e.preventDefault(); pick(options[active]); }
            else e.currentTarget.blur();
          }
        }}
        className={cx(
          "h-9 w-full rounded-control border bg-bg pl-2.5 pr-8 text-[14px] text-ink placeholder:text-muted disabled:opacity-60",
          open ? "border-action ring-2 ring-action-soft" : "border-line-strong focus:border-action",
        )}
      />
      <ChevronDown size={15} aria-hidden className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-body" />
      {open && pos && options.length ? (
        <Menu id={id} pos={pos} options={options} value={value} active={active} onPick={pick} onHover={setActive} listRef={list} />
      ) : null}
    </div>
  );
}
