// DEVELOPMENT MOCK ONLY. A small stand-in for server/lectern/engine/place.py so the mock API can
// answer /render. The real layout engine lives in the backend; nothing in the app imports this file.

import type { ElementStyle, Node, RenderedSlide, Slide, SlideElement, Theme } from "@/lib/types";

const M = 120;
const W = 1920;

type Placed = { node: Node; i: number };

export function place(slide: Slide, theme: Theme): RenderedSlide {
  const c = theme.colors;
  const els: SlideElement[] = [];
  let n = 0;
  const add = (e: Omit<SlideElement, "id">) => els.push({ id: `${slide.id}-e${n++}`, ...e });
  const text = (node: number | null, x: number, y: number, w: number, h: number, value: string, style: ElementStyle) =>
    add({ kind: "text", node, x, y, w, h, text: value, style });
  const rect = (x: number, y: number, w: number, h: number, fill: string) =>
    add({ kind: "rect", node: null, x, y, w, h, style: { fill } });

  const all: Placed[] = slide.nodes.map((node, i) => ({ node, i }));
  const pick = (role: string) => all.find((p) => p.node.type === "text" && p.node.role === role);
  const headline = pick("headline");
  const eyebrow = pick("eyebrow");
  const caption = pick("caption");
  const headText = headline && headline.node.type === "text" ? headline.node.value : slide.headline;
  const headNode = headline ? headline.i : null;
  let blocks = all.filter((p) => p !== headline && p !== eyebrow && p !== caption);

  let background = c.bg;
  let ink = c.ink;
  let body = c.body;
  let muted = c.muted;

  const eyebrowAt = (x: number, y: number, w: number, color = muted) => {
    if (eyebrow && eyebrow.node.type === "text")
      text(eyebrow.i, x, y, w, 32, eyebrow.node.value, { font_size: 22, font_weight: 700, color, uppercase: true, letter_spacing: 0.08 });
  };

  const block = (p: Placed, x: number, y: number, w: number, h: number) => {
    const node = p.node;
    switch (node.type) {
      case "text":
        text(p.i, x, y, w, h, node.value, { font_size: node.role === "subhead" ? 38 : 32, color: body, line_height: 1.35 });
        break;
      case "bullets":
        add({ kind: "text", node: p.i, x, y, w, h, bullets: node.items, style: { font_size: 34, color: body, line_height: 1.3 } });
        break;
      case "stat": {
        const size = Math.round(Math.min(200, h * 0.5, (w / Math.max(3, node.value.length)) * 1.5));
        text(p.i, x, y, w, size * 1.1, node.value, { font_size: size, font_weight: 700, color: ink, line_height: 1.05, letter_spacing: -0.03 });
        if (node.caption) text(p.i, x, y + size * 1.1 + 12, w, 90, node.caption, { font_size: 30, color: body, line_height: 1.3 });
        if (node.source) text(p.i, x, y + h - 34, w, 30, node.source, { font_size: 20, color: muted });
        break;
      }
      case "chart": {
        let top = y;
        if (node.title) {
          text(p.i, x, y, w, 36, node.title, { font_size: 24, font_weight: 700, color: muted });
          top += 52;
        }
        add({
          kind: "chart", node: p.i, x, y: top, w, h: h - (top - y),
          chart: { kind: node.kind, categories: node.categories, series: node.series, colors: theme.chart_colors, unit: node.unit },
        });
        break;
      }
      case "table":
        add({ kind: "table", node: p.i, x, y, w, h, table: { columns: node.columns, rows: node.rows }, style: { font_size: 28, color: ink } });
        break;
      case "image":
        add({ kind: "image", node: p.i, x, y, w, h, src: node.src, alt: node.alt, style: { fill: c.surface } });
        break;
      case "quote":
        text(p.i, x, y, w, h - 70, `“${node.text}”`, { font_size: 52, font_weight: 700, color: ink, line_height: 1.2, valign: "middle" });
        if (node.attribution) text(p.i, x, y + h - 56, w, 44, node.attribution, { font_size: 28, color: muted });
        break;
      case "items": {
        const k = Math.max(1, node.items.length);
        const gap = 48;
        const cw = (w - gap * (k - 1)) / k;
        if (node.style === "timeline") add({ kind: "line", node: null, x, y: y + 70, w, h: 0, style: { stroke: c.line, stroke_width: 4 } });
        node.items.forEach((item, j) => {
          const cx = x + j * (cw + gap);
          let cy = y;
          if (node.style === "steps") {
            text(null, cx, cy, cw, 70, String(j + 1).padStart(2, "0"), { font_size: 56, font_weight: 700, color: c.accent });
            cy += 96;
          } else if (node.style === "timeline") {
            if (item.label) text(p.i, cx, cy, cw, 36, item.label, { font_size: 24, font_weight: 700, color: muted, uppercase: true, letter_spacing: 0.06 });
            rect(cx, cy + 58, 24, 24, j === k - 1 ? c.accent : ink);
            cy += 120;
          } else {
            rect(cx, cy, cw, 6, j === 0 ? c.accent : ink);
            cy += 36;
            if (item.label) {
              text(p.i, cx, cy, cw, 32, item.label, { font_size: 22, font_weight: 700, color: muted, uppercase: true, letter_spacing: 0.06 });
              cy += 48;
            }
          }
          text(p.i, cx, cy, cw, 100, item.title, { font_size: k > 4 ? 30 : 38, font_weight: 700, color: ink, line_height: 1.15 });
          if (item.body) text(p.i, cx, cy + (k > 4 ? 90 : 112), cw, Math.max(60, y + h - cy - 112), item.body, { font_size: k > 4 ? 24 : 28, color: body, line_height: 1.35 });
        });
        break;
      }
    }
  };

  const weight = (p: Placed) =>
    p.node.type === "chart" || p.node.type === "table" || p.node.type === "image" || p.node.type === "items" ? 3
      : p.node.type === "text" ? 1 : 2;

  const stack = (list: Placed[], x: number, y: number, w: number, h: number) => {
    const gap = 36;
    const total = list.reduce((a, p) => a + weight(p), 0) || 1;
    const usable = h - gap * (list.length - 1);
    let cy = y;
    list.forEach((p) => {
      const bh = (usable * weight(p)) / total;
      block(p, x, cy, w, bh);
      cy += bh + gap;
    });
  };

  const isVisual = (p: Placed) => p.node.type === "chart" || p.node.type === "table" || p.node.type === "image";

  const layout = slide.layout;
  if (layout === "title" || layout === "closing" || layout === "section") {
    if (layout === "closing") {
      background = c.ink;
      ink = c.bg;
      body = "#C9CBD3";
      muted = "#C9CBD3";
    } else if (layout === "section") {
      background = c.surface;
    }
    const image = blocks.find((p) => p.node.type === "image");
    const tw = image ? 1000 : 1500;
    rect(M, M, 96, 16, c.accent);
    eyebrowAt(M, 180, tw);
    text(headNode, M, 330, tw, 420, headText, { font_size: layout === "title" ? 112 : 96, font_weight: 700, color: ink, line_height: 1.02, letter_spacing: -0.03, valign: "bottom" });
    const others = blocks.filter((p) => p !== image);
    if (others.length) stack(others, M, 790, tw, 180);
    if (image) block(image, 1240, 0, 680, 1080);
  } else if (layout === "quote" && blocks.some((p) => p.node.type === "quote")) {
    const quote = blocks.find((p) => p.node.type === "quote")!;
    rect(M, M, 96, 16, c.accent);
    text(headNode, M, 170, 1680, 44, headText, { font_size: 28, font_weight: 700, color: muted });
    block(quote, M, 260, 1560, 640);
    blocks = blocks.filter((p) => p !== quote);
  } else if ((layout === "big_number" || layout === "big_idea") && blocks.some((p) => p.node.type === "stat")) {
    const stat = blocks.find((p) => p.node.type === "stat")!;
    const rest = blocks.filter((p) => p !== stat);
    eyebrowAt(M, 96, 940);
    text(headNode, M, eyebrow ? 146 : 96, 940, 230, headText, { font_size: 68, font_weight: 700, color: ink, line_height: 1.08, letter_spacing: -0.02 });
    if (rest.length) stack(rest, M, 420, 940, 540);
    rect(1160, 96, 640, 888, c.accent);
    if (stat.node.type === "stat") {
      const size = Math.min(220, Math.round(900 / Math.max(3, stat.node.value.length)));
      text(stat.i, 1210, 560 - size * 0.2, 540, size * 1.1, stat.node.value, { font_size: size, font_weight: 700, color: c.on_accent, line_height: 1, letter_spacing: -0.04 });
      if (stat.node.caption) text(stat.i, 1210, 800, 540, 100, stat.node.caption, { font_size: 32, font_weight: 700, color: c.on_accent, line_height: 1.25 });
      if (stat.node.source) text(stat.i, 1210, 920, 540, 30, stat.node.source, { font_size: 20, color: c.on_accent });
    }
  } else {
    eyebrowAt(M, 88, 1680);
    text(headNode, M, eyebrow ? 132 : 96, 1680, 150, headText, { font_size: 60, font_weight: 700, color: ink, line_height: 1.1, letter_spacing: -0.02 });
    let y = 300;
    let h = 660;
    const stats = blocks.filter((p) => p.node.type === "stat");
    if (stats.length > 1) {
      const gap = 40;
      const sw = (W - 2 * M - gap * (stats.length - 1)) / stats.length;
      stats.forEach((p, j) => {
        rect(M + j * (sw + gap), y, sw, 250, c.surface);
        if (p.node.type === "stat") {
          text(p.i, M + j * (sw + gap) + 32, y + 28, sw - 64, 110, p.node.value, { font_size: 88, font_weight: 700, color: ink, letter_spacing: -0.03 });
          if (p.node.caption) text(p.i, M + j * (sw + gap) + 32, y + 150, sw - 64, 80, p.node.caption, { font_size: 26, color: body, line_height: 1.3 });
        }
      });
      blocks = blocks.filter((p) => !stats.includes(p));
      y += 290;
      h -= 290;
    }
    const visuals = blocks.filter(isVisual);
    const others = blocks.filter((p) => !isVisual(p));
    if (visuals.length && others.length) {
      stack(others, M, y, 700, h);
      stack(visuals, 900, y, 900, h);
    } else if (layout === "two_column" && blocks.length > 1) {
      const half = Math.ceil(blocks.length / 2);
      stack(blocks.slice(0, half), M, y, 800, h);
      stack(blocks.slice(half), 1000, y, 800, h);
    } else if (blocks.length) {
      stack(blocks, M, y, 1680, h);
    }
  }

  if (caption && caption.node.type === "text") text(caption.i, M, 1000, 1680, 30, caption.node.value, { font_size: 20, color: muted });

  return { id: slide.id, index: slide.index, width: 1920, height: 1080, background, elements: els };
}
