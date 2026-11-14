"use client";

import { ImageIcon } from "lucide-react";
import { memo, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { RenderedSlide, SlideElement } from "@/lib/types";
import { cx } from "@/lib/format";
import { ChartSvg } from "./ChartSvg";

const STAGE_W = 1920;
const STAGE_H = 1080;

function isDark(hex: string): boolean {
  const m = /^#?([0-9a-f]{6}|[0-9a-f]{3})$/i.exec(hex.trim());
  if (!m) return false;
  const h = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 110;
}

/** Letter spacing in the scene graph is a bare number: small values are read as em, larger ones as canvas px. */
function spacing(v: number | undefined): string | undefined {
  if (v === undefined || v === 0) return undefined;
  return Math.abs(v) < 1 ? `${v}em` : `${v}px`;
}

function textStyle(el: SlideElement, dark: boolean): CSSProperties {
  const s = el.style ?? {};
  return {
    fontSize: s.font_size ?? 28,
    fontWeight: s.font_weight ?? 400,
    color: s.color ?? (dark ? "#FFFFFF" : "#16181D"),
    textAlign: s.align ?? "left",
    lineHeight: s.line_height ?? 1.25,
    letterSpacing: spacing(s.letter_spacing),
    textTransform: s.uppercase ? "uppercase" : undefined,
  };
}

const JUSTIFY = { top: "flex-start", middle: "center", bottom: "flex-end" } as const;

function box(el: SlideElement): CSSProperties {
  return { position: "absolute", left: el.x, top: el.y, width: el.w, height: el.h };
}

/** The text a person edits for this element: bullets are one per line. */
export function editableText(el: SlideElement): string {
  if (el.bullets?.length) return el.bullets.join("\n");
  return el.text ?? "";
}

function TextBody({ el }: { el: SlideElement }) {
  return (
    <>
      {el.text ? <div style={{ whiteSpace: "pre-wrap", overflowWrap: "break-word" }}>{el.text}</div> : null}
      {el.bullets?.map((b, i) => (
        <div key={i} style={{ display: "flex", gap: "0.6em", marginTop: i || el.text ? "0.5em" : 0 }}>
          <span aria-hidden style={{ flexShrink: 0, width: "0.3em", height: "0.3em", marginTop: "0.48em", borderRadius: "50%", background: "currentColor" }} />
          <span style={{ whiteSpace: "pre-wrap", overflowWrap: "break-word", minWidth: 0 }}>{b}</span>
        </div>
      ))}
    </>
  );
}

function EditableText({
  el, dark, scale, onCommit,
}: { el: SlideElement; dark: boolean; scale: number; onCommit: (el: SlideElement, text: string) => void }) {
  const [editing, setEditing] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cancelled = useRef(false);
  const px = 1 / Math.max(scale, 0.05); // one screen pixel in canvas units

  useEffect(() => {
    if (!editing || !ref.current) return;
    const node = ref.current;
    node.focus();
    const range = document.createRange();
    range.selectNodeContents(node);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);
  }, [editing]);

  function finish() {
    const next = (ref.current?.innerText ?? "").replace(/ /g, " ").replace(/\n+$/, "");
    setEditing(false);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    if (next.trim() && next !== editableText(el)) onCommit(el, next);
  }

  const frame: CSSProperties = {
    ...box(el),
    ...textStyle(el, dark),
    display: "flex",
    flexDirection: "column",
    justifyContent: JUSTIFY[el.style?.valign ?? "top"],
  };

  if (!editing) {
    return (
      <div
        style={{ ...frame, cursor: "text", ["--px" as string]: `${px}px` }}
        className="lectern-editable"
        role="button"
        tabIndex={0}
        aria-label={`Edit text: ${editableText(el).slice(0, 80)}`}
        onClick={() => setEditing(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setEditing(true);
          }
        }}
      >
        <TextBody el={el} />
      </div>
    );
  }
  return (
    <div style={{ ...frame, outline: `${1.5 * px}px solid var(--action)`, outlineOffset: 6 * px, zIndex: 5 }}>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label="Slide text"
        spellCheck
        style={{ whiteSpace: "pre-wrap", overflowWrap: "break-word", outline: "none", minHeight: "1em" }}
        onBlur={finish}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            cancelled.current = true;
            ref.current?.blur();
          } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey || !el.bullets?.length)) {
            // Enter saves; in a bullet list Enter starts a new bullet and Ctrl+Enter saves.
            e.preventDefault();
            ref.current?.blur();
          }
        }}
      >
        {editableText(el)}
      </div>
    </div>
  );
}

function ElementView({ el, dark, background }: { el: SlideElement; dark: boolean; background: string }) {
  const s = el.style ?? {};
  switch (el.kind) {
    case "text":
      return (
        <div style={{ ...box(el), ...textStyle(el, dark), display: "flex", flexDirection: "column", justifyContent: JUSTIFY[s.valign ?? "top"] }}>
          <TextBody el={el} />
        </div>
      );
    case "rect":
      return (
        <div
          style={{
            ...box(el),
            background: s.fill,
            border: s.stroke ? `${s.stroke_width ?? 2}px solid ${s.stroke}` : undefined,
            borderRadius: s.radius,
            boxSizing: "border-box",
          }}
        />
      );
    case "line":
      return (
        <svg style={{ position: "absolute", left: el.x, top: el.y, overflow: "visible" }} width={Math.max(1, el.w)} height={Math.max(1, el.h)} aria-hidden>
          <line x1={0} y1={0} x2={el.w} y2={el.h} stroke={s.stroke ?? s.color ?? (dark ? "#FFFFFF" : "#16181D")} strokeWidth={s.stroke_width ?? 2} />
        </svg>
      );
    case "chart":
      return el.chart ? (
        <div style={box(el)}>
          <ChartSvg chart={el.chart} w={el.w} h={el.h} dark={dark} surface={background} />
        </div>
      ) : null;
    case "table": {
      if (!el.table) return null;
      const ink = s.color ?? (dark ? "#FFFFFF" : "#16181D");
      const numeric = (v: string) => /^[\s$€£+\-−]?[\d.,]+\s?[%kKmMbB×x]?$/.test(v.trim());
      return (
        <div style={{ ...box(el), overflow: "hidden", fontSize: s.font_size ?? 26, lineHeight: s.line_height ?? 1.25, color: ink }}>
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <thead>
              <tr>
                {el.table.columns.map((c, i) => (
                  <th key={i} style={{ textAlign: i === 0 ? "left" : "right", fontWeight: 700, padding: "0.5em 0.6em", borderBottom: `3px solid ${ink}` }}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {el.table.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, i) => (
                    <td
                      key={i}
                      style={{
                        textAlign: i === 0 ? "left" : numeric(cell) ? "right" : "right",
                        fontWeight: i === 0 ? 700 : 400,
                        padding: "0.5em 0.6em",
                        borderBottom: `2px solid ${dark ? "#3A3D46" : "#E8E8EC"}`,
                        overflowWrap: "break-word",
                      }}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    case "image":
      return el.src ? (
        // Slide pictures come from the API at arbitrary sizes; next/image adds nothing here.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={el.src} alt={el.alt ?? ""} style={{ ...box(el), objectFit: "cover" }} />
      ) : (
        <div
          style={{ ...box(el), background: s.fill ?? (dark ? "#2A2D35" : "#EFEFF2"), color: dark ? "#C9CBD3" : "#7A7F8C", fontSize: 26, lineHeight: 1.3 }}
          className="flex flex-col items-center justify-center gap-4 p-10 text-center"
        >
          <ImageIcon size={56} strokeWidth={1.5} aria-hidden />
          {el.alt ? <span style={{ maxWidth: "80%" }}>{el.alt}</span> : null}
        </div>
      );
    default:
      return null;
  }
}

type Props = {
  slide: RenderedSlide;
  /** Fixed width in px. Leave out to fill the container (measured with a ResizeObserver). */
  width?: number;
  className?: string;
  /** Text elements this returns true for can be clicked and edited in place. */
  canEdit?: (el: SlideElement) => boolean;
  onEditText?: (el: SlideElement, text: string) => void;
};

/**
 * Draws a RenderedSlide as absolutely positioned elements on a 1920 x 1080 stage,
 * scaled to its container with a CSS transform. Used for thumbnails and the main stage.
 */
export const SlideCanvas = memo(function SlideCanvas({ slide, width, className, canEdit, onEditText }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState(0);

  useLayoutEffect(() => {
    if (width !== undefined || !ref.current) return;
    const node = ref.current;
    setMeasured(node.clientWidth);
    const ro = new ResizeObserver(() => setMeasured(node.clientWidth));
    ro.observe(node);
    return () => ro.disconnect();
  }, [width]);

  const w = width ?? measured;
  const scale = w / STAGE_W;
  const dark = isDark(slide.background);
  const interactive = Boolean(canEdit && onEditText);

  return (
    <div
      ref={ref}
      className={cx("relative shrink-0 overflow-hidden", className)}
      style={{ width: width ?? "100%", aspectRatio: "16 / 9", background: slide.background }}
      role={interactive ? "group" : "img"}
      aria-label={`Slide ${slide.index}`}
    >
      {scale > 0 ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            width: STAGE_W,
            height: STAGE_H,
            transform: `scale(${scale})`,
            transformOrigin: "0 0",
            pointerEvents: interactive ? undefined : "none",
          }}
        >
          {slide.elements.map((el) =>
            interactive && el.kind === "text" && canEdit!(el) ? (
              <EditableText key={el.id} el={el} dark={dark} scale={scale} onCommit={onEditText!} />
            ) : (
              <ElementView key={el.id} el={el} dark={dark} background={slide.background} />
            ),
          )}
        </div>
      ) : null}
    </div>
  );
});

/** Placeholder with the same footprint as a slide, for slides that are not drawn yet. */
export function SlidePlaceholder({ width, label, dashed, className }: { width?: number; label?: string; dashed?: boolean; className?: string }) {
  return (
    <div
      className={cx("flex shrink-0 items-center justify-center text-[13px] font-bold text-muted", dashed ? "border border-dashed border-line-strong bg-bg" : "bg-surface", className)}
      style={{ width: width ?? "100%", aspectRatio: "16 / 9" }}
    >
      {label}
    </div>
  );
}
