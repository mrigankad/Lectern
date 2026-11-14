"""Developer aid: print the deck the offline provider writes for a prompt, with lint findings.

    uv run python scripts/offline_demo.py "Your prompt" [out.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lectern.engine.lint import lint_slide  # noqa: E402
from lectern.engine.place import place_deck  # noqa: E402
from lectern.llm.offline.provider import OfflineProvider  # noqa: E402
from lectern.schema import Slide  # noqa: E402


def build(prompt: str) -> list[Slide]:
    provider = OfflineProvider()
    brief = {"prompt": prompt}
    outline = provider._outline({"brief": brief})
    entries = [{"index": i + 1, **s} for i, s in enumerate(outline["slides"])]
    slides = []
    for entry in entries:
        draft = provider._write_slide({"brief": brief, "slide": entry, "outline": entries})
        slides.append(Slide.model_validate({"id": f"s{entry['index']}", "index": entry["index"],
                                            "section": entry["section"], "intent": entry["intent"],
                                            "status": "ready", **draft}))
    print(outline["title"], "|", outline["deck_type"])
    return slides


def main() -> None:
    slides = build(sys.argv[1])
    for slide in slides:
        print(f"{slide.index:>2} {slide.layout:<13} {slide.headline}")
        for node in slide.nodes[1:]:
            print("      ", node.model_dump(exclude_none=True))
        for issue in lint_slide(slide):
            print("      !!", issue.rule, "-", issue.detail)
    if len(sys.argv) > 2:
        from preview import sheet
        sheet(place_deck(slides), sys.argv[2], cols=3)


if __name__ == "__main__":
    main()
