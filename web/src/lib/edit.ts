import type { Node, Slide, SlideElement, SlidePatch } from "./types";

/**
 * Maps a text element on the rendered slide back to the piece of slide content it shows.
 *
 * A rendered element only carries the index of its node, and one node can produce several
 * text boxes (a stat has a value, a caption and a source). So the box is matched to the node
 * field whose text it shows. If nothing matches, the box is not editable in place.
 */

type Field = { get: () => string; set: (v: string) => Node };

const QUOTES = /^[“"‘']+|[”"’']+$/g;
const same = (a: string | undefined, b: string | undefined) => a !== undefined && b !== undefined && a.trim() === b.trim();

function fields(node: Node): Field[] {
  switch (node.type) {
    case "text":
      return [{ get: () => node.value, set: (v) => ({ ...node, value: v }) }];
    case "stat":
      return [
        { get: () => node.value, set: (v) => ({ ...node, value: v }) },
        { get: () => node.caption ?? "", set: (v) => ({ ...node, caption: v }) },
        { get: () => node.source ?? "", set: (v) => ({ ...node, source: v }) },
      ];
    case "quote":
      return [
        { get: () => node.text, set: (v) => ({ ...node, text: v.replace(QUOTES, "") }) },
        { get: () => node.attribution ?? "", set: (v) => ({ ...node, attribution: v }) },
      ];
    case "chart":
      return [{ get: () => node.title ?? "", set: (v) => ({ ...node, title: v }) }];
    case "items":
      return node.items.flatMap((item, i) => {
        const put = (patch: Partial<typeof item>): Node => ({ ...node, items: node.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
        return [
          { get: () => item.title, set: (v: string) => put({ title: v }) },
          { get: () => item.body ?? "", set: (v: string) => put({ body: v }) },
          { get: () => item.label ?? "", set: (v: string) => put({ label: v }) },
        ];
      });
    default:
      return [];
  }
}

function locate(slide: Slide, el: SlideElement): ((text: string) => Node) | null {
  if (el.kind !== "text" || el.node === null || el.node === undefined) return null;
  const node = slide.nodes[el.node];
  if (!node) return null;
  if (node.type === "bullets") {
    // One element holding the whole list: one bullet per line.
    if (el.bullets?.length)
      return (text) => ({ ...node, items: text.split("\n").map((l) => l.replace(/^[\s•·\-–*]+/, "").trim()).filter(Boolean) });
    // The backend draws each bullet as its own text element: edit just that item.
    const at = el.text ? node.items.findIndex((item) => same(item, el.text)) : -1;
    if (at < 0) return null;
    return (text) => ({ ...node, items: node.items.map((item, i) => (i === at ? text.replace(/\n+/g, " ").trim() : item)) });
  }
  if (!el.text) return null;
  const shown = el.text;
  const field = fields(node).find((f) => f.get() && (same(f.get(), shown) || same(f.get(), shown.replace(QUOTES, ""))));
  return field ? field.set : null;
}

export function canEditElement(slide: Slide, el: SlideElement): boolean {
  return locate(slide, el) !== null;
}

/** The PATCH body for an in-place text edit, or null when the element cannot be mapped. */
export function textEditPatch(slide: Slide, el: SlideElement, text: string): SlidePatch | null {
  const set = locate(slide, el);
  if (!set || el.node === null || el.node === undefined) return null;
  const next = set(text);
  const nodes = slide.nodes.map((n, i) => (i === el.node ? next : n));
  const patch: SlidePatch = { nodes };
  if (next.type === "text" && next.role === "headline") patch.headline = next.value;
  return patch;
}
