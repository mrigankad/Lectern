"""Key-based media providers over their documented HTTP APIs: Google (Imagen, Veo), OpenAI Images,
FLUX on fal.ai, Runway, and Pexels stock. All network calls go through `media.http` so tests can mock them."""
from __future__ import annotations

import base64

from . import http
from .base import Kind, MediaError, MediaResult, full_prompt, image_size, require_kind, size_of

GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_BASE = "https://api.openai.com/v1"
FAL_BASE = "https://fal.run"
RUNWAY_BASE = "https://api.dev.runwayml.com/v1"
PEXELS_BASE = "https://api.pexels.com"


class _Keyed:
    id = ""
    label = ""
    kinds: tuple[Kind, ...] = ("image",)

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        if not api_key:
            raise MediaError(f"Add an API key for {self.label} first.")
        self.api_key = api_key
        self.base_url = (base_url or self.default_base()).rstrip("/")

    def default_base(self) -> str:
        return ""

    async def test(self) -> tuple[bool, str]:
        try:
            await self._ping()
        except MediaError as error:
            return False, str(error)
        return True, f"{self.label} accepted the key."

    async def _ping(self) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------- Google: Imagen and Veo
class GoogleProvider(_Keyed):
    id, label = "google", "Google Imagen and Veo"
    kinds = ("image", "video")
    image_model = "imagen-4.0-generate-001"
    video_model = "veo-3.0-fast-generate-001"

    def default_base(self) -> str:
        return GOOGLE_BASE

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key}

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        text = full_prompt(prompt, style)
        if kind == "image":
            data = await http.json("POST", f"{self.base_url}/models/{self.image_model}:predict", self.label,
                                   headers=self._headers(),
                                   json={"instances": [{"prompt": text}],
                                         "parameters": {"sampleCount": 1, "aspectRatio": aspect}})
            results = []
            for prediction in data.get("predictions") or []:
                raw = base64.b64decode(prediction.get("bytesBase64Encoded", ""))
                if raw:
                    w, h = image_size(raw)
                    results.append(MediaResult(data=raw, mime=prediction.get("mimeType", "image/png"), width=w,
                                               height=h, cost_estimate=0.04, meta={"model": self.image_model}))
            if not results:
                raise MediaError("Imagen returned no image (the prompt may have been filtered).")
            return results
        ratio = "9:16" if aspect in {"9:16", "3:4"} else "16:9"
        operation = await http.json("POST", f"{self.base_url}/models/{self.video_model}:predictLongRunning",
                                    self.label, headers=self._headers(),
                                    json={"instances": [{"prompt": text}], "parameters": {"aspectRatio": ratio}})
        name = operation.get("name")
        if not name:
            raise MediaError("Veo did not start a job.")
        done = await http.poll(lambda: http.json("GET", f"{self.base_url}/{name}", self.label, headers=self._headers()),
                               lambda op: bool(op.get("done")),
                               lambda op: (op.get("error") or {}).get("message"), self.label, interval=8)
        samples = (((done.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples") or [])
        uri = samples[0].get("video", {}).get("uri") if samples else None
        if not uri:
            raise MediaError("Veo finished but returned no video.")
        response = await http.request("GET", uri, self.label, headers=self._headers(), follow_redirects=True)
        w, h = (1280, 720) if ratio == "16:9" else (720, 1280)
        return [MediaResult(data=response.content, mime="video/mp4", kind="video", width=w, height=h,
                            cost_estimate=1.2, meta={"model": self.video_model})]

    async def _ping(self) -> None:
        await http.json("GET", f"{self.base_url}/models", self.label, headers=self._headers())


# ---------------------------------------------------------------- OpenAI Images
class OpenAIImagesProvider(_Keyed):
    id, label = "openai_images", "OpenAI Images"
    model = "gpt-image-1"

    def default_base(self) -> str:
        return OPENAI_BASE

    @staticmethod
    def size_for(aspect: str) -> str:
        w, h = size_of(aspect)
        return "1536x1024" if w > h else "1024x1536" if h > w else "1024x1024"

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        data = await http.json("POST", f"{self.base_url}/images/generations", self.label,
                               headers={"Authorization": f"Bearer {self.api_key}"},
                               json={"model": self.model, "prompt": full_prompt(prompt, style),
                                     "size": self.size_for(aspect), "n": 1})
        results = []
        for item in data.get("data") or []:
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                raw, _ = await http.download(item["url"], self.label)
            else:
                continue
            w, h = image_size(raw)
            results.append(MediaResult(data=raw, width=w, height=h, cost_estimate=0.04, meta={"model": self.model}))
        if not results:
            raise MediaError("OpenAI returned no image.")
        return results

    async def _ping(self) -> None:
        await http.json("GET", f"{self.base_url}/models", self.label,
                        headers={"Authorization": f"Bearer {self.api_key}"})


# ---------------------------------------------------------------- FLUX on fal.ai
FAL_SIZES = {"16:9": "landscape_16_9", "4:3": "landscape_4_3", "1:1": "square_hd", "3:4": "portrait_4_3",
             "9:16": "portrait_16_9"}


class FluxProvider(_Keyed):
    id, label = "flux", "FLUX (fal.ai)"
    model = "fal-ai/flux/schnell"

    def default_base(self) -> str:
        return FAL_BASE

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self.api_key}"}

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        data = await http.json("POST", f"{self.base_url}/{self.model}", self.label, headers=self._headers(),
                               json={"prompt": full_prompt(prompt, style), "image_size": FAL_SIZES.get(aspect,
                                     "landscape_16_9"), "num_images": 1})
        results = []
        for image in data.get("images") or []:
            raw, mime = await http.download(image["url"], self.label)
            w, h = image.get("width") or 0, image.get("height") or 0
            if not (w and h):
                w, h = image_size(raw)
            results.append(MediaResult(data=raw, mime=mime if mime.startswith("image/") else "image/jpeg", width=w,
                                       height=h, cost_estimate=0.003, meta={"model": self.model}))
        if not results:
            raise MediaError("FLUX returned no image.")
        return results

    async def _ping(self) -> None:
        # fal has no free key check; a malformed request returns 422 with a valid key and 401 without one.
        try:
            await http.request("POST", f"{self.base_url}/{self.model}", self.label, headers=self._headers(), json={})
        except MediaError as error:
            if error.status not in (400, 422):
                raise


# ---------------------------------------------------------------- Runway
RUNWAY_IMAGE_RATIOS = {"16:9": "1920:1080", "4:3": "1440:1080", "1:1": "1024:1024", "3:4": "1080:1440",
                       "9:16": "1080:1920"}


class RunwayProvider(_Keyed):
    id, label = "runway", "Runway"
    kinds = ("video", "image")
    video_model = "veo3.1_fast"
    image_model = "gen4_image"

    def default_base(self) -> str:
        return RUNWAY_BASE

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "X-Runway-Version": "2024-11-06"}

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        text = full_prompt(prompt, style)[:1000]
        if kind == "video":
            ratio = "720:1280" if aspect in {"9:16", "3:4"} else "1280:720"
            body = {"model": self.video_model, "promptText": text, "ratio": ratio, "duration": 8}
            task = await http.json("POST", f"{self.base_url}/text_to_video", self.label, headers=self._headers(),
                                   json=body)
        else:
            ratio = RUNWAY_IMAGE_RATIOS.get(aspect, "1920:1080")
            body = {"model": self.image_model, "promptText": text, "ratio": ratio}
            task = await http.json("POST", f"{self.base_url}/text_to_image", self.label, headers=self._headers(),
                                   json=body)
        task_id = task.get("id")
        if not task_id:
            raise MediaError("Runway did not start a task.")
        done = await http.poll(lambda: http.json("GET", f"{self.base_url}/tasks/{task_id}", self.label,
                                                 headers=self._headers()),
                               lambda t: t.get("status") == "SUCCEEDED",
                               lambda t: (t.get("failure") or "Runway reported a failure.")
                               if t.get("status") in {"FAILED", "CANCELLED"} else None,
                               self.label, interval=5)
        w, h = (int(x) for x in ratio.split(":"))
        results = []
        for url in done.get("output") or []:
            raw, mime = await http.download(url, self.label)
            results.append(MediaResult(data=raw, kind=kind, mime=mime if "/" in mime else
                                       ("video/mp4" if kind == "video" else "image/png"), width=w, height=h,
                                       cost_estimate=0.8 if kind == "video" else 0.08,
                                       meta={"model": body["model"]}))
        if not results:
            raise MediaError("Runway finished but returned no file.")
        return results

    async def _ping(self) -> None:
        await http.json("GET", f"{self.base_url}/organization", self.label, headers=self._headers())


# ---------------------------------------------------------------- Stock (Pexels)
class StockProvider(_Keyed):
    """Stock photos and clips from Pexels. Returns nothing unless a key is configured."""
    id, label = "stock", "Stock (Pexels)"
    kinds = ("image", "video")

    def default_base(self) -> str:
        return PEXELS_BASE

    async def generate(self, prompt: str, kind: Kind, aspect: str, style: str) -> list[MediaResult]:
        require_kind(self, kind)
        w, h = size_of(aspect)
        orientation = "landscape" if w > h else "portrait" if h > w else "square"
        headers = {"Authorization": self.api_key}
        query = {"query": prompt[:100], "orientation": orientation, "per_page": 2}
        results = []
        if kind == "image":
            data = await http.json("GET", f"{self.base_url}/v1/search", self.label, headers=headers, params=query)
            for photo in data.get("photos") or []:
                raw, mime = await http.download(photo["src"].get("large2x") or photo["src"]["original"], self.label)
                pw, ph = image_size(raw)
                results.append(MediaResult(data=raw, mime=mime, width=pw, height=ph, cost_estimate=0.0,
                                           meta={"source": photo.get("url"), "credit": photo.get("photographer")}))
        else:
            data = await http.json("GET", f"{self.base_url}/videos/search", self.label, headers=headers, params=query)
            for video in data.get("videos") or []:
                files = sorted((f for f in video.get("video_files") or [] if f.get("file_type") == "video/mp4"),
                               key=lambda f: f.get("width") or 0)
                if not files:
                    continue
                chosen = next((f for f in files if (f.get("width") or 0) >= 1280), files[-1])
                raw, _ = await http.download(chosen["link"], self.label)
                poster = None
                if video.get("image"):
                    poster, _ = await http.download(video["image"], self.label)
                results.append(MediaResult(data=raw, mime="video/mp4", kind="video", width=chosen.get("width") or 0,
                                           height=chosen.get("height") or 0, poster=poster, cost_estimate=0.0,
                                           meta={"source": video.get("url")}))
        return results

    async def _ping(self) -> None:
        await http.json("GET", f"{self.base_url}/v1/curated", self.label, headers={"Authorization": self.api_key},
                        params={"per_page": 1})
