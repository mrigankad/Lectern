"""Runtime configuration, read from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent

CANVAS_W = 1920
CANVAS_H = 1080
BUILD_CONCURRENCY = 3

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "gemini": "GEMINI_API_KEY",
    # media providers
    "google": "GEMINI_API_KEY",
    "openai_images": "OPENAI_API_KEY",
    "flux": "FAL_KEY",
    "runway": "RUNWAYML_API_SECRET",
    "stock": "PEXELS_API_KEY",
}


def data_dir() -> Path:
    path = Path(os.environ.get("LECTERN_DATA_DIR") or SERVER_DIR / "data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "lectern.db"


def exports_dir() -> Path:
    path = data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_dir() -> Path:
    path = data_dir() / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def higgsfield_bin() -> str | None:
    """The Higgsfield CLI executable. Prefers the vendored hf.exe behind the npm shim so no shell is involved."""
    import shutil

    explicit = os.environ.get("LECTERN_HIGGSFIELD_BIN")
    if explicit:
        return explicit
    found = shutil.which("higgsfield")
    if not found:
        return None
    if found.lower().endswith((".cmd", ".ps1")) or not Path(found).suffix:
        vendored = Path(found).parent / "node_modules" / "@higgsfield" / "cli" / "vendor" / "hf.exe"
        if vendored.exists():
            return str(vendored)
    return found


def references_dir() -> Path:
    return Path(os.environ.get("LECTERN_REFERENCES_DIR") or REPO_DIR / "references")


def offline_delay() -> float:
    """Seconds the offline provider waits per agent step so the live build is watchable."""
    try:
        return max(0.0, float(os.environ.get("LECTERN_OFFLINE_DELAY", "0.6")))
    except ValueError:
        return 0.6


def cors_origins() -> list[str]:
    raw = os.environ.get("LECTERN_CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def force_offline() -> bool:
    return os.environ.get("LECTERN_FORCE_OFFLINE", "").lower() in {"1", "true", "yes"}


def env_key(connection_id: str) -> str | None:
    """API key supplied through the environment for a connection, if any."""
    name = _ENV_KEYS.get(connection_id)
    value = os.environ.get(name) if name else None
    return value or None
