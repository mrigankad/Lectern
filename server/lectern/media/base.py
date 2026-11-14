"""The media provider interface: one `generate` call per provider, returning stored-ready results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..llm.base import LLMError

Kind = Literal["image", "video"]
ASPECTS: dict[str, tuple[int, int]] = {
    "16:9": (1600, 900), "4:3": (1600, 1200), "1:1": (1200, 1200), "3:4": (1200, 1600), "9:16": (900, 1600),
}
DEFAULT_STYLE = "flat, clean, matches deck theme"


class MediaError(LLMError):
    """A media provider call failed. `retryable` marks 429, 5xx and connection errors."""


@dataclass
class MediaResult:
    data: bytes
    mime: str = "image/png"
    kind: Kind = "image"
    width: int = 0
    height: int = 0
    poster: bytes | None = None          # video poster frame (PNG/JPEG/WebP bytes)
    cost_estimate: float | None = None   # provider units (credits or USD), as reported or estimated
    meta: dict[str, Any] = field(default_factory=dict)


class MediaProvider(Protocol):
    id: str
    kinds: tuple[Kind, ...]

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]: ...

    async def test(self) -> tuple[bool, str]: ...


def size_of(aspect: str) -> tuple[int, int]:
    return ASPECTS.get(aspect, ASPECTS["16:9"])


def full_prompt(prompt: str, style: str) -> str:
    prompt = prompt.strip()
    style = (style or "").strip()
    return f"{prompt}. Style: {style}." if style and style.lower() not in prompt.lower() else prompt


def image_size(data: bytes) -> tuple[int, int]:
    """Pixel size of image bytes, (0, 0) when unreadable."""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.size
    except Exception:
        return 0, 0


def require_kind(provider: MediaProvider, kind: Kind) -> None:
    if kind not in provider.kinds:
        raise MediaError(f"{provider.id} cannot make {kind}s.")
