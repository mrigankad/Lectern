"""Check a slide's nodes against a layout's slots and adapt content when the layout changes."""
from __future__ import annotations

import re

from ..schema import BulletsNode, Item, ItemsNode, Node, Slot, TableNode, TextNode
from .registry import get_layout, required_slots


def _fills(slot: Slot, node: Node) -> bool:
    if isinstance(node, TextNode):
        if not node.value.strip():
            return False
        if slot.type == "text":
            return node.role == slot.role
        return "text" in slot.accepts and node.role in {"body", "subhead"}
    if node.type != slot.type and node.type not in slot.accepts:
        return False
    if isinstance(node, (BulletsNode, ItemsNode)):
        return bool(node.items)
    return True


def slot_filled(slot: Slot, nodes: list[Node]) -> bool:
    return any(_fills(slot, node) for node in nodes)


def missing_slots(layout_id: str, nodes: list[Node]) -> list[Slot]:
    """Required slots of the layout that no node fills."""
    return [slot for slot in required_slots(layout_id) if not slot_filled(slot, nodes)]


def bullet_to_item(text: str) -> Item:
    text = text.strip()
    match = re.match(r"^(.{3,48}?)\s*(?::|\s[-–—]\s)\s*(.+)$", text)
    if match:
        return Item(title=match.group(1).strip(), body=match.group(2).strip())
    words = text.split()
    if len(words) <= 7:
        return Item(title=text)
    clause = re.split(r"[,;]\s+", text, maxsplit=1)
    if len(clause) == 2 and 2 <= len(clause[0].split()) <= 7:
        return Item(title=clause[0], body=clause[1])
    return Item(title=" ".join(words[:5]), body=text)


def item_to_bullet(item: Item) -> str:
    if item.body and item.body.strip() and item.body.strip() != item.title.strip():
        return f"{item.title}: {item.body}".replace("\n", "; ")
    return item.title


def adapt_nodes(nodes: list[Node], layout_id: str) -> list[Node]:
    """Convert list-like content so it fills the target layout's required slot.

    Bullets become items (and the reverse), and an items node takes the style the layout draws.
    Content that cannot be converted is left as it is; the caller reports the empty slot.
    """
    result = list(nodes)
    for slot in get_layout(layout_id).slots:
        if slot.name == "headline":
            continue
        if slot.type == "items":
            index = _find(result, "items")
            if index is not None:
                node = result[index]
                assert isinstance(node, ItemsNode)
                if slot.style and node.style != slot.style:
                    result[index] = node.model_copy(update={"style": slot.style})
                continue
            index = _find(result, "bullets")
            if index is not None and slot.required:
                node = result[index]
                assert isinstance(node, BulletsNode)
                result[index] = ItemsNode(style=slot.style or "columns",  # type: ignore[arg-type]
                                          items=[bullet_to_item(b) for b in node.items])
        elif slot.type == "bullets" and slot.required:
            if _find(result, "bullets") is not None:
                continue
            index = _find(result, "items")
            if index is not None:
                node = result[index]
                assert isinstance(node, ItemsNode)
                result[index] = BulletsNode(items=[item_to_bullet(i) for i in node.items])
        elif slot.type == "table" and slot.required and "items" not in slot.accepts:
            if _find(result, "table") is not None:
                continue
            index = _find(result, "items")
            if index is not None:
                node = result[index]
                assert isinstance(node, ItemsNode)
                result[index] = TableNode(columns=["Item", "Detail"],
                                          rows=[[i.title, i.body or i.label or ""] for i in node.items])
    return result


def ensure_headline(nodes: list[Node], headline: str) -> list[Node]:
    """Guarantee exactly one headline text node, first in the list, matching the slide headline."""
    rest = [n for n in nodes if not (isinstance(n, TextNode) and n.role == "headline")]
    return [TextNode(role="headline", value=headline), *rest]


def _find(nodes: list[Node], node_type: str) -> int | None:
    for index, node in enumerate(nodes):
        if node.type == node_type:
            return index
    return None
