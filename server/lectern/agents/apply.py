"""Apply a content change to a stored slide: normalise, save a version, re-lint, announce."""
from __future__ import annotations

from typing import Any

from .. import store
from ..models import SlideRow
from ..schema import Node, Slide
from . import renderer


def dump_nodes(nodes: list[Node]) -> list[dict[str, Any]]:
    return [node.model_dump(exclude_none=True) for node in nodes]


def patched(slide: Slide, *, headline: str | None = None, layout: str | None = None,
            nodes: list[Node] | None = None, notes: str | None = None) -> Slide:
    """The slide with a patch applied and normalised for its (possibly new) layout."""
    update: dict[str, Any] = {}
    if headline is not None and headline.strip():
        update["headline"] = headline.strip()
    if layout is not None:
        update["layout"] = layout
    if nodes is not None:
        if any(getattr(n, "data_ref", None) or getattr(n, "source", None) for n in nodes):
            from ..sources.link import fill_linked  # an edit that links a chart gets its values from the cells
            nodes = fill_linked(list(nodes))
        update["nodes"] = nodes
    if notes is not None:
        update["notes"] = notes
    return renderer.normalize(slide.model_copy(update=update))


def save(deck_id: str, slide: Slide, reason: str, *, section: str | None = None, lint: bool = True,
         announce: bool = True) -> tuple[SlideRow, str | None]:
    """Store the slide's content as a new version. Returns (row, version id or None when nothing changed)."""
    row, version_id = store.save_slide(slide.id, reason, headline=slide.headline, layout=slide.layout,
                                       nodes=dump_nodes(slide.nodes), notes=slide.notes, section=section)
    if lint:
        store.lint_and_sync(deck_id, slide.id)
        row = store.get_slide_row(deck_id, slide.id)
    if announce:
        store.publish_slide(row)
    return row, version_id
