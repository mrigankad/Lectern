"""The layout registry."""
from __future__ import annotations

from fastapi import APIRouter

from ..layouts import registry
from ..schema import LayoutInfo

router = APIRouter(tags=["layouts"])


@router.get("/layouts", response_model=list[LayoutInfo], response_model_exclude_none=True)
async def list_layouts() -> list[LayoutInfo]:
    return list(registry().values())
