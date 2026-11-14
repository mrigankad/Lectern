"""Media: the router, every provider (network mocked), endpoints, placement, the Art Director hook and export."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from lectern.media import higgsfield, http
from lectern.media import router as media
from lectern.media.base import MediaError, MediaResult
from lectern.media.keyed import (FluxProvider, GoogleProvider, OpenAIImagesProvider, RunwayProvider,
                                 StockProvider)
from lectern.media.offline import OfflineMediaProvider, draw

from .conftest import build_deck


def png(width: int = 64, height: int = 36, color: str = "#2563EB") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture()
def mock_http(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Route every media HTTP call to a handler; records requests."""
    calls: list[httpx.Request] = []
    state: dict[str, Any] = {"handler": None}

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return state["handler"](request)

    monkeypatch.setattr(http, "client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(transport)))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(http, "sleep", no_sleep)
    state["calls"] = calls
    return state


def wait_job(client: TestClient, deck_id: str, job_id: str, timeout: float = 15) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = next(j for j in client.get(f"/api/decks/{deck_id}/media/jobs").json() if j["id"] == job_id)
        if job["status"] in {"done", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("media job did not finish")


# ---------------------------------------------------------------- offline
def test_offline_is_deterministic_and_themed() -> None:
    a = draw("Revenue growth chart", "16:9")
    assert a == draw("Revenue growth chart", "16:9")
    assert a != draw("Our team", "16:9")
    with Image.open(io.BytesIO(a)) as image:
        assert image.size == (1600, 900)
    results = run(OfflineMediaProvider().generate("A team", "image", "9:16", "flat"))
    assert results[0].width == 900 and results[0].height == 1600
    with pytest.raises(MediaError):
        run(OfflineMediaProvider().generate("x", "video", "16:9", ""))


# ---------------------------------------------------------------- key-based providers
def test_google_imagen_and_veo(mock_http) -> None:  # type: ignore[no-untyped-def]
    image = png()
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "g-key"
        if request.url.path.endswith(":predict"):
            body = json.loads(request.content)
            assert body["parameters"]["aspectRatio"] == "4:3"
            return httpx.Response(200, json={"predictions": [{"bytesBase64Encoded": base64.b64encode(image).decode(),
                                                              "mimeType": "image/png"}]})
        if request.url.path.endswith(":predictLongRunning"):
            return httpx.Response(200, json={"name": "operations/op1"})
        if request.url.path.endswith("/operations/op1"):
            polls["n"] += 1
            if polls["n"] < 2:
                return httpx.Response(200, json={"done": False})
            return httpx.Response(200, json={"done": True, "response": {"generateVideoResponse": {
                "generatedSamples": [{"video": {"uri": "https://files.example/v.mp4"}}]}}})
        if request.url.host == "files.example":
            return httpx.Response(200, content=b"MP4DATA")
        return httpx.Response(404)

    mock_http["handler"] = handler
    provider = GoogleProvider("g-key")
    images = run(provider.generate("A chart", "image", "4:3", "flat"))
    assert images[0].data == image and images[0].width == 64
    videos = run(provider.generate("A chart", "video", "16:9", "flat"))
    assert videos[0].kind == "video" and videos[0].data == b"MP4DATA" and polls["n"] == 2


def test_openai_images(mock_http) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer o-key"
        body = json.loads(request.content)
        assert body["size"] == "1536x1024" and "flat" in body["prompt"]
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})

    mock_http["handler"] = handler
    results = run(OpenAIImagesProvider("o-key").generate("Growth", "image", "16:9", "flat, clean"))
    assert len(results) == 1 and results[0].mime == "image/png"


def test_flux_fal(mock_http) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "fal.run":
            assert request.headers["authorization"] == "Key f-key"
            assert json.loads(request.content)["image_size"] == "square_hd"
            return httpx.Response(200, json={"images": [{"url": "https://cdn.fal/x.jpg", "width": 1024,
                                                         "height": 1024}]})
        return httpx.Response(200, content=png(), headers={"content-type": "image/jpeg"})

    mock_http["handler"] = handler
    results = run(FluxProvider("f-key").generate("Growth", "image", "1:1", ""))
    assert results[0].width == 1024 and results[0].mime == "image/jpeg"


def test_runway_video_polls_until_done(mock_http) -> None:  # type: ignore[no-untyped-def]
    states = iter(["PENDING", "RUNNING", "SUCCEEDED"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/text_to_video"):
            assert request.headers["x-runway-version"] == "2024-11-06"
            return httpx.Response(200, json={"id": "t1"})
        if request.url.path.endswith("/tasks/t1"):
            status = next(states)
            return httpx.Response(200, json={"status": status, "output": ["https://r.example/v.mp4"]
                                             if status == "SUCCEEDED" else None})
        return httpx.Response(200, content=b"VIDEO", headers={"content-type": "video/mp4"})

    mock_http["handler"] = handler
    results = run(RunwayProvider("r-key").generate("Launch", "video", "16:9", ""))
    assert results[0].kind == "video" and results[0].width == 1280


def test_runway_failure_is_reported(mock_http) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/text_to_video"):
            return httpx.Response(200, json={"id": "t2"})
        return httpx.Response(200, json={"status": "FAILED", "failure": "content moderation"})

    mock_http["handler"] = handler
    with pytest.raises(MediaError, match="content moderation"):
        run(RunwayProvider("r-key").generate("x", "video", "16:9", ""))


def test_stock_pexels(mock_http) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/search":
            assert request.headers["authorization"] == "p-key"
            return httpx.Response(200, json={"photos": [{"url": "u", "photographer": "A",
                                                         "src": {"large2x": "https://img.example/a.png"}}]})
        return httpx.Response(200, content=png(), headers={"content-type": "image/png"})

    mock_http["handler"] = handler
    results = run(StockProvider("p-key").generate("office", "image", "16:9", ""))
    assert results[0].meta["credit"] == "A"


def test_keyed_providers_need_a_key() -> None:
    with pytest.raises(MediaError, match="API key"):
        GoogleProvider("")


def test_retries_with_backoff_on_429(mock_http) -> None:  # type: ignore[no-untyped-def]
    answers = iter([httpx.Response(429), httpx.Response(503),
                    httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png()).decode()}]})])
    mock_http["handler"] = lambda _request: next(answers)
    media.set_provider_override("openai_images", OpenAIImagesProvider("o-key"))
    delays: list[float] = []

    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    results = run(media.generate_with("openai_images", "x", "image", "16:9", "", sleep=sleep))
    assert len(results) == 1 and len(delays) == 2 and delays[1] > delays[0] * 0.9


def test_auth_errors_are_not_retried(mock_http) -> None:  # type: ignore[no-untyped-def]
    mock_http["handler"] = lambda _request: httpx.Response(401)
    media.set_provider_override("openai_images", OpenAIImagesProvider("bad"))
    with pytest.raises(MediaError, match="rejected the API key"):
        run(media.generate_with("openai_images", "x", "image", "16:9", ""))
    assert len(mock_http["calls"]) == 1


# ---------------------------------------------------------------- Higgsfield (CLI mocked: it bills real credits)
def test_higgsfield_runs_cli_and_downloads(monkeypatch: pytest.MonkeyPatch, mock_http) -> None:  # type: ignore[no-untyped-def]
    commands: list[list[str]] = []

    async def fake_run(args: list[str], _timeout: float) -> tuple[int, str, str]:
        commands.append(args)
        if args[1:3] == ["generate", "cost"]:
            return 0, '{"credits": 0.25}', ""
        return 0, json.dumps([{"id": "j1", "status": "completed",
                               "result_url": "https://cdn.hf/x.png", "min_result_url": None}]), ""

    monkeypatch.setattr(higgsfield, "run", fake_run)
    mock_http["handler"] = lambda _request: httpx.Response(200, content=png(), headers={"content-type": "image/png"})
    results = run(higgsfield.HiggsfieldProvider("hf.exe").generate('Rising "bars" & more', "image", "16:9", "flat"))
    assert results[0].cost_estimate == 0.25 and results[0].width == 64
    create = commands[-1]
    assert create[:4] == ["hf.exe", "generate", "create", "gpt_image_2_5"]
    assert "--wait" in create and create[create.index("--aspect_ratio") + 1] == "16:9"
    assert any('Rising "bars" & more' in part for part in create)   # passed as one argv item, no shell


def test_higgsfield_explains_missing_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(args: list[str], _timeout: float) -> tuple[int, str, str]:
        if args[1:3] == ["generate", "cost"]:
            return 0, '{"credits": 0.25}', ""
        return 3, "", 'Error: {"error_type":"not_enough_credits"}'

    monkeypatch.setattr(higgsfield, "run", fake_run)
    with pytest.raises(MediaError, match="enough credits"):
        run(higgsfield.HiggsfieldProvider("hf.exe").generate("x", "image", "16:9", ""))


def test_higgsfield_test_reads_account(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(args: list[str], _timeout: float) -> tuple[int, str, str]:
        assert args[1:3] == ["account", "status"]
        return 0, '{"credits": 12.5, "subscription_plan_type": "pro"}', ""

    monkeypatch.setattr(higgsfield, "run", fake_run)
    ok, detail = run(higgsfield.HiggsfieldProvider("hf.exe").test())
    assert ok and "12.5" in detail


def test_higgsfield_parses_mixed_output() -> None:
    out = 'Waiting for job...\n{"jobs": [{"result_url": "https://a/b.mp4", "min_result_url": "https://a/b.webp"}]}'
    assert higgsfield.result_urls(higgsfield.parse_json(out)) == [("https://a/b.mp4", "https://a/b.webp")]


# ---------------------------------------------------------------- router, connections and settings
def test_media_connections_listed_and_testable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    connections = client.get("/api/settings/connections").json()
    kinds = {c["id"]: c["kind"] for c in connections}
    for provider_id in ("higgsfield", "google", "openai_images", "flux", "runway", "stock"):
        assert kinds[provider_id] == "media"
    # a media key never changes model routing
    client.put("/api/settings/connections", json={"id": "flux", "api_key": "f-key"})
    assert client.get("/api/health").json()["provider"] == "offline"
    providers = {p["id"]: p for p in client.get("/api/media/providers").json()}
    assert providers["offline"]["connected"] and providers["flux"]["connected"]
    assert not providers["google"]["connected"] and providers["flux"]["is_default"]
    assert client.post("/api/settings/connections/google/test").json() == {"ok": False,
                                                                           "detail": "Add an API key first."}

    async def fake_run(args: list[str], _timeout: float) -> tuple[int, str, str]:
        return 0, '{"credits": 3}', ""

    monkeypatch.setattr(higgsfield, "run", fake_run)
    monkeypatch.setattr("lectern.config.higgsfield_bin", lambda: "hf.exe")
    assert not providers["higgsfield"]["connected"]
    result = client.post("/api/settings/connections/higgsfield/test").json()
    assert result["ok"] and "3 credits" in result["detail"]
    assert {p["id"]: p for p in client.get("/api/media/providers").json()}["higgsfield"]["connected"]
    bad = client.put("/api/settings/routing", json={"roles": {"writer": {"provider": "flux", "model": "x"}}})
    assert bad.status_code == 409


def test_media_settings(client: TestClient) -> None:
    assert client.get("/api/settings/media").json()["auto_images"] is False
    assert client.put("/api/settings/media", json={"auto_images": True}).json()["auto_images"] is True
    assert client.put("/api/settings/media", json={"default_provider": "nope"}).status_code == 409


# ---------------------------------------------------------------- endpoints and placement
def test_generate_list_download_and_place(client: TestClient) -> None:
    deck = build_deck(client)
    slide = next(s for s in deck["slides"] if s["layout"] == "title")
    suggestion = client.get(f"/api/decks/{deck['id']}/media/suggest", params={"slide_id": slide["id"]}).json()
    assert slide["headline"] in suggestion["prompt"] and suggestion["style"].startswith("flat")
    job = client.post(f"/api/decks/{deck['id']}/media/generate",
                      json={"slide_id": slide["id"], "prompt": suggestion["prompt"], "kind": "image",
                            "aspect": "16:9", "providers": ["offline"]})
    assert job.status_code == 202
    done = wait_job(client, deck["id"], job.json()["id"])
    assert done["status"] == "done" and len(done["asset_ids"]) == 1
    assets = client.get(f"/api/decks/{deck['id']}/media", params={"slide_id": slide["id"]}).json()
    asset = assets[0]
    assert asset["provider"] == "offline" and asset["width"] == 1600 and asset["url"].endswith("/file")
    downloaded = client.get(asset["url"])
    assert downloaded.status_code == 200 and downloaded.headers["content-type"] == "image/png"
    assert media.file_of(media.get_asset(asset["id"])).parent.name == deck["id"]
    placed = client.post(f"/api/decks/{deck['id']}/slides/{slide['id']}/media", json={"asset_id": asset["id"]})
    assert placed.status_code == 200
    body = placed.json()
    assert body["layout"] == "big_idea"   # the title layout draws no picture, so it switches
    images = [n for n in body["nodes"] if n["type"] == "image"]
    assert len(images) == 1 and images[0]["asset_id"] == asset["id"]
    rendered = client.get(f"/api/decks/{deck['id']}/slides/{slide['id']}/render").json()
    assert any(e["kind"] == "image" and e["src"] == asset["url"] for e in rendered["elements"])
    # placing again replaces the image instead of adding a second one
    again = client.post(f"/api/decks/{deck['id']}/slides/{slide['id']}/media", json={"asset_id": asset["id"]}).json()
    assert sum(1 for n in again["nodes"] if n["type"] == "image") == 1


def test_generate_validation(client: TestClient) -> None:
    deck = build_deck(client)
    url = f"/api/decks/{deck['id']}/media/generate"
    assert client.post(url, json={"prompt": "x", "providers": ["google"]}).status_code == 409   # not connected
    assert client.post(url, json={"prompt": "x", "providers": ["nope"]}).status_code == 409
    assert client.post(url, json={"prompt": "x", "aspect": "7:5"}).status_code == 409
    assert client.post(url, json={"prompt": "x", "kind": "video", "providers": ["offline"]}).status_code == 409
    assert client.post(url, json={"prompt": " "}).status_code == 409


def test_one_failing_provider_keeps_the_others(client: TestClient) -> None:
    class Broken:
        id = "flux"
        kinds = ("image",)

        async def generate(self, *_args: Any) -> list[MediaResult]:
            raise MediaError("FLUX is down.")

        async def test(self) -> tuple[bool, str]:
            return True, ""

    media.set_provider_override("flux", Broken())
    deck = build_deck(client)
    job = client.post(f"/api/decks/{deck['id']}/media/generate",
                      json={"prompt": "Growth chart", "providers": ["offline", "flux"]}).json()
    done = wait_job(client, deck["id"], job["id"])
    assert done["status"] == "done" and len(done["asset_ids"]) == 1
    assert done["errors"] == [{"provider": "flux", "detail": "FLUX is down."}]


def test_video_job_stores_poster(client: TestClient) -> None:
    class FakeVideo:
        id = "runway"
        kinds = ("video",)

        async def generate(self, *_args: Any) -> list[MediaResult]:
            return [MediaResult(data=b"MP4", mime="video/mp4", kind="video", width=1280, height=720)]

        async def test(self) -> tuple[bool, str]:
            return True, ""

    media.set_provider_override("runway", FakeVideo())
    deck = build_deck(client)
    job = client.post(f"/api/decks/{deck['id']}/media/generate",
                      json={"prompt": "Launch film", "kind": "video", "providers": ["runway"]}).json()
    done = wait_job(client, deck["id"], job["id"])
    asset = client.get(f"/api/decks/{deck['id']}/media", params={"kind": "video"}).json()[0]
    assert done["status"] == "done" and asset["poster_url"]
    assert client.get(asset["poster_url"]).headers["content-type"] == "image/png"
    assert client.get(asset["url"]).content == b"MP4"


def test_upload(client: TestClient) -> None:
    deck = build_deck(client)
    url = f"/api/decks/{deck['id']}/media/upload"
    ok = client.post(url, params={"filename": "logo.png"}, content=png(200, 100),
                     headers={"content-type": "image/png"})
    assert ok.status_code == 200 and ok.json()["provider"] == "upload" and ok.json()["width"] == 200
    assert client.post(url, content=b"hello", headers={"content-type": "text/plain"}).status_code == 409
    assert client.post(url, content=b"", headers={"content-type": "image/png"}).status_code == 409
    assert client.get("/api/media/ma_000000000000/file").status_code == 404


def test_deleting_a_deck_removes_its_media(client: TestClient, data_dir: Path) -> None:
    deck = build_deck(client)
    client.post(f"/api/decks/{deck['id']}/media/upload", content=png(), headers={"content-type": "image/png"})
    assert (data_dir / "media" / deck["id"]).is_dir()
    client.delete(f"/api/decks/{deck['id']}")
    assert not (data_dir / "media" / deck["id"]).exists()


# ---------------------------------------------------------------- Art Director
def test_no_automatic_images_by_default(client: TestClient) -> None:
    deck = build_deck(client)
    assert client.get(f"/api/decks/{deck['id']}/media").json() == []


def test_auto_images_setting_uses_offline_placeholders(client: TestClient) -> None:
    client.put("/api/settings/media", json={"auto_images": True})
    deck = build_deck(client)
    assets = client.get(f"/api/decks/{deck['id']}/media").json()
    wanted = [s for s in deck["slides"] if any(n["type"] == "image" for n in s["nodes"])]
    assert assets and all(a["provider"] == "offline" for a in assets)
    assert len(wanted) == len(assets)
    assert all(s["layout"] in media.WANTS_PICTURE for s in wanted)


def test_default_provider_is_used_when_configured(client: TestClient) -> None:
    class Fake:
        id = "flux"
        kinds = ("image",)
        prompts: list[str] = []

        async def generate(self, prompt: str, *_args: Any) -> list[MediaResult]:
            self.prompts.append(prompt)
            return [MediaResult(data=png(), width=64, height=36)]

        async def test(self) -> tuple[bool, str]:
            return True, ""

    fake = Fake()
    client.put("/api/settings/connections", json={"id": "flux", "api_key": "f-key"})
    media.set_provider_override("flux", fake)
    deck = build_deck(client)
    assets = client.get(f"/api/decks/{deck['id']}/media").json()
    assert all(a["provider"] == "flux" for a in assets)
    assert len(fake.prompts) == len(assets)
    assert all("No text" in p for p in fake.prompts)


# ---------------------------------------------------------------- export
def test_export_places_stored_assets_as_pictures(client: TestClient) -> None:
    deck = build_deck(client)
    slide = next(s for s in deck["slides"] if s["layout"] not in ("title", "section", "closing", "case_study"))
    asset = client.post(f"/api/decks/{deck['id']}/media/upload", content=png(320, 180),
                        headers={"content-type": "image/png"}).json()
    client.post(f"/api/decks/{deck['id']}/slides/{slide['id']}/media", json={"asset_id": asset["id"]})
    # and a video on another slide: exported as its poster frame plus a note
    class FakeVideo:
        id = "runway"
        kinds = ("video",)

        async def generate(self, *_args: Any) -> list[MediaResult]:
            return [MediaResult(data=b"MP4", mime="video/mp4", kind="video", width=1280, height=720)]

        async def test(self) -> tuple[bool, str]:
            return True, ""

    media.set_provider_override("runway", FakeVideo())
    other = next(s for s in deck["slides"] if s["id"] != slide["id"])
    job = client.post(f"/api/decks/{deck['id']}/media/generate",
                      json={"prompt": "Launch film", "kind": "video", "providers": ["runway"]}).json()
    video_id = wait_job(client, deck["id"], job["id"])["asset_ids"][0]
    client.post(f"/api/decks/{deck['id']}/slides/{other['id']}/media", json={"asset_id": video_id})

    out = client.post(f"/api/decks/{deck['id']}/export", json={"format": "pptx", "include_notes": True}).json()
    report = out["report"]
    assert report["pictures"] == 2
    assert next(c for c in report["checks"] if c["label"].startswith("Pictures"))["ok"]
    assert next(c for c in report["checks"] if c["label"] == "Speaker notes")["ok"]
    prs = Presentation(io.BytesIO(client.get(f"/api/files/{out['file_id']}").content))
    pictures = [shape for page in prs.slides for shape in page.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 2
    notes = [page.notes_slide.notes_text_frame.text for page in prs.slides if page.has_notes_slide]
    assert any("poster frame of a video" in text for text in notes)
