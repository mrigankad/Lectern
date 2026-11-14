"""The structured outputs agents return. Their JSON schemas are what providers are asked to fill."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..schema import LayoutId, Node


class OutlineSlide(BaseModel):
    section: str | None = Field(default=None, description="Short section label, e.g. 'The risk'.")
    headline: str = Field(description="The slide's claim: one sentence with a verb, 12 words or fewer.")
    layout: LayoutId
    intent: str = Field(default="", description="One line: what this slide is for.")


class OutlineDraft(BaseModel):
    title: str = Field(description="Deck title, a few words.")
    deck_type: str | None = Field(default=None, description="The deck type from the reference list that fits.")
    slides: list[OutlineSlide]


class SlideDraft(BaseModel):
    headline: str = Field(description="The slide's claim, 12 words or fewer.")
    nodes: list[Node] = Field(description="Content nodes for the layout's slots. No coordinates.")
    notes: str = Field(description="Speaker notes: what to say that is not on the slide.")


class LayoutChoice(BaseModel):
    layout: LayoutId
    reason: str = Field(default="", description="One short sentence.")


class SlideEdit(BaseModel):
    """A patch to one slide. Omit a field to leave it unchanged."""
    headline: str | None = None
    layout: LayoutId | None = None
    nodes: list[Node] | None = None
    notes: str | None = None
    summary: str = Field(description="One plain sentence saying what changed, for the chat.")


class SlideChange(BaseModel):
    slide_id: str
    headline: str | None = None
    layout: LayoutId | None = None
    nodes: list[Node] | None = None
    notes: str | None = None


class DeckEdit(BaseModel):
    """A patch to several slides."""
    title: str | None = None
    changes: list[SlideChange] = Field(default_factory=list)
    remove_slide_ids: list[str] = Field(default_factory=list,
                                        description="Slides to delete, only when the user asks for a shorter deck.")
    summary: str = Field(description="One plain sentence saying what changed, for the chat.")


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()
