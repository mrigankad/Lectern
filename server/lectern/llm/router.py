"""Provider router: connections, routing presets, and the one entry point agents call (`complete`)."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlmodel import select

from .. import config
from ..db import session
from ..models import ConnectionRow, RoleRouteRow
from ..schema import ROLES, Connection, RoleRoute, Routing
from .anthropic_provider import AnthropicProvider
from .claude_code import ClaudeCodeProvider
from .base import LLMError, LLMRequest, LLMResult, Provider
from .offline.provider import MODEL as OFFLINE_MODEL
from .offline.provider import OfflineProvider
from .openai_compatible import OpenAICompatibleProvider
from .retry import with_retries

T = TypeVar("T", bound=BaseModel)
PRESET_KEY = "_preset"
CREATIVE_ROLES = ("strategist", "writer", "art_director", "editor")
CHECKING_ROLES = ("renderer", "critic")


@dataclass(frozen=True)
class Seed:
    id: str
    label: str
    kind: str
    base_url: str | None
    top: str       # most capable model
    strong: str    # everyday model for writing roles
    fast: str      # cheapest model, for checking roles
    needs_key: bool = True


# Anthropic model ids follow SPEC section 7. The ids for other vendors are starting points that
# the user can change per role in model routing.
SEEDS: tuple[Seed, ...] = (
    Seed("offline", "Offline (built in)", "offline", None, OFFLINE_MODEL, OFFLINE_MODEL, OFFLINE_MODEL, False),
    Seed("anthropic", "Anthropic", "anthropic", None, "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
    Seed("claude_code", "Claude Code (local login)", "model", None, "opus", "sonnet", "haiku", False),
    Seed("openai", "OpenAI", "openai_compatible", "https://api.openai.com/v1", "gpt-5", "gpt-5-mini", "gpt-5-nano"),
    Seed("openrouter", "OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1",
         "openai/gpt-5", "openai/gpt-5-mini", "openai/gpt-5-nano"),
    Seed("gemini", "Google Gemini", "openai_compatible",
         "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-pro", "gemini-2.5-flash",
         "gemini-2.5-flash-lite"),
    Seed("groq", "Groq", "openai_compatible", "https://api.groq.com/openai/v1",
         "llama-3.3-70b-versatile", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    Seed("deepseek", "DeepSeek", "openai_compatible", "https://api.deepseek.com/v1",
         "deepseek-reasoner", "deepseek-chat", "deepseek-chat"),
    Seed("mistral", "Mistral", "openai_compatible", "https://api.mistral.ai/v1",
         "mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"),
    Seed("litellm", "LiteLLM gateway", "openai_compatible", "http://localhost:4000/v1",
         "gpt-5", "gpt-5-mini", "gpt-5-mini", False),
    Seed("ollama", "Ollama (local)", "openai_compatible", "http://localhost:11434/v1",
         "llama3.1", "llama3.1", "llama3.1", False),
)
SEED_BY_ID = {seed.id: seed for seed in SEEDS}

PRESETS = [
    {"id": "best_quality", "label": "Best quality",
     "description": "The most capable model writes and plans; a strong model checks."},
    {"id": "balanced", "label": "Balanced",
     "description": "A strong model writes and plans; a fast model checks."},
    {"id": "lowest_cost", "label": "Lowest cost", "description": "The fastest, cheapest model does everything."},
]
PRESET_IDS = {p["id"] for p in PRESETS}

_provider_override: Provider | None = None


def set_provider_override(provider: Provider | None) -> None:
    """Route every role to one provider instance (tests use this to stub a model)."""
    global _provider_override
    _provider_override = provider


# ---------------------------------------------------------------- connections
def seed_defaults() -> None:
    with session() as s:
        for position, seed in enumerate(SEEDS):
            if s.get(ConnectionRow, seed.id) is None:
                s.add(ConnectionRow(id=seed.id, label=seed.label, kind=seed.kind, base_url=seed.base_url,
                                    status="connected" if seed.kind == "offline" else "not_configured",
                                    position=position))
        s.commit()
        if s.get(RoleRouteRow, PRESET_KEY) is None:
            s.add(RoleRouteRow(role=PRESET_KEY, provider="balanced", model=""))
            s.commit()
    apply_preset(current_preset())


def key_of(row: ConnectionRow) -> str | None:
    return row.api_key or config.env_key(row.id)


def is_usable(row: ConnectionRow) -> bool:
    if row.kind == "offline":
        return True
    if config.force_offline():
        return False
    seed = SEED_BY_ID.get(row.id)
    if seed is not None and not seed.needs_key:
        return row.status == "connected"      # local gateways count once a test has succeeded
    return bool(key_of(row))


def to_connection(row: ConnectionRow) -> Connection:
    has_key = bool(key_of(row))
    status = row.status
    if row.kind != "offline" and status == "not_configured" and has_key:
        status = "configured"
    return Connection(id=row.id, label=row.label, kind=row.kind, base_url=row.base_url, has_key=has_key,
                      status=status, detail=row.detail)


def list_connections() -> list[Connection]:
    with session() as s:
        rows = s.exec(select(ConnectionRow).order_by(ConnectionRow.position)).all()
    return [to_connection(row) for row in rows]


def get_connection(connection_id: str) -> ConnectionRow | None:
    with session() as s:
        return s.get(ConnectionRow, connection_id)


def update_connection(connection_id: str, api_key: str | None, base_url: str | None) -> bool:
    """Store a key and/or base URL. An empty string clears the value. Returns False if unknown."""
    with session() as s:
        row = s.get(ConnectionRow, connection_id)
        if row is None or row.kind == "offline":
            return row is not None
        if api_key is not None:
            row.api_key = api_key.strip() or None
        if base_url is not None:
            seed = SEED_BY_ID.get(row.id)
            row.base_url = base_url.strip() or (seed.base_url if seed else None)
        row.status = "configured" if key_of(row) else "not_configured"
        row.detail = None
        s.add(row)
        s.commit()
    if current_preset() in PRESET_IDS:
        apply_preset(current_preset())
    return True


def build_provider(row: ConnectionRow) -> Provider:
    if row.kind == "anthropic":
        return AnthropicProvider(api_key=key_of(row) or "", base_url=row.base_url)
    if row.id == "claude_code":
        return ClaudeCodeProvider()
    if row.kind == "openai_compatible":
        return OpenAICompatibleProvider(row.id, row.base_url or "", key_of(row))
    return OfflineProvider()


async def test_connection(connection_id: str) -> tuple[bool, str, list[str] | None] | None:
    row = get_connection(connection_id)
    if row is None:
        return None
    if row.kind == "media":
        from ..media import router as media_router
        return await media_router.test_connection(connection_id)
    seed = SEED_BY_ID.get(row.id)
    if row.kind != "offline" and seed is not None and seed.needs_key and not key_of(row):
        ok, detail, models = False, "Add an API key first.", None
    else:
        ok, detail, models = await build_provider(row).test()
    if row.kind != "offline":
        with session() as s:
            fresh = s.get(ConnectionRow, connection_id)
            if fresh is not None:
                fresh.status = "connected" if ok else ("error" if key_of(fresh) or not (seed and seed.needs_key)
                                                       else "not_configured")
                fresh.detail = detail
                s.add(fresh)
                s.commit()
        if current_preset() in PRESET_IDS:
            apply_preset(current_preset())
    return ok, detail, models


# ---------------------------------------------------------------- routing
def current_preset() -> str:
    with session() as s:
        row = s.get(RoleRouteRow, PRESET_KEY)
    return row.provider if row else "balanced"


def best_connection() -> ConnectionRow:
    """The first usable model provider in the seed order; the offline provider when there is none."""
    with session() as s:
        rows = s.exec(select(ConnectionRow).order_by(ConnectionRow.position)).all()
    for row in rows:
        if row.kind not in ("offline", "media") and is_usable(row):
            return row
    return next(row for row in rows if row.kind == "offline")


def preset_routes(preset: str, connection_id: str) -> dict[str, RoleRoute]:
    seed = SEED_BY_ID.get(connection_id, SEEDS[0])
    if preset == "best_quality":
        creative, checking = seed.top, seed.strong
    elif preset == "lowest_cost":
        creative, checking = seed.fast, seed.fast
    else:
        creative, checking = seed.strong, seed.fast
    routes = {role: RoleRoute(provider=seed.id, model=creative) for role in CREATIVE_ROLES}
    routes.update({role: RoleRoute(provider=seed.id, model=checking) for role in CHECKING_ROLES})
    return routes


def _store_routes(preset: str, routes: dict[str, RoleRoute]) -> None:
    with session() as s:
        marker = s.get(RoleRouteRow, PRESET_KEY) or RoleRouteRow(role=PRESET_KEY)
        marker.provider = preset
        s.add(marker)
        for role, route in routes.items():
            row = s.get(RoleRouteRow, role) or RoleRouteRow(role=role)
            row.provider, row.model = route.provider, route.model
            s.add(row)
        s.commit()


def apply_preset(preset: str) -> None:
    if preset not in PRESET_IDS:
        return
    _store_routes(preset, preset_routes(preset, best_connection().id))


def normalize_preset(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def get_routing() -> Routing:
    with session() as s:
        rows = {row.role: row for row in s.exec(select(RoleRouteRow)).all()}
    roles = {role: RoleRoute(provider=rows[role].provider, model=rows[role].model) if role in rows
             else RoleRoute(provider="offline", model=OFFLINE_MODEL) for role in ROLES}
    preset = rows[PRESET_KEY].provider if PRESET_KEY in rows else "balanced"
    return Routing(preset=preset, roles=roles, presets=PRESETS)


def set_routing(preset: str | None, roles: dict[str, RoleRoute] | None) -> Routing:
    """Apply a preset, explicit per-role routes, or both (explicit routes win and mark it custom)."""
    if preset is not None:
        preset = normalize_preset(preset)
        if preset not in PRESET_IDS and preset != "custom":
            raise ValueError("Unknown preset. Use Best quality, Balanced or Lowest cost.")
    if roles:
        unknown = [role for role in roles if role not in ROLES]
        if unknown:
            raise ValueError(f"Unknown role: {unknown[0]}.")
        for role, route in roles.items():
            target = get_connection(route.provider)
            if target is not None and target.kind == "media":
                raise ValueError(f"\"{route.provider}\" makes images and videos, not text. Pick a model provider for {role}.")
            if target is None:
                raise ValueError(f"Unknown provider \"{route.provider}\" for {role}.")
    if preset in PRESET_IDS:
        apply_preset(preset)
    if roles:
        expected = preset_routes(preset, best_connection().id) if preset in PRESET_IDS else {}
        differs = any(expected.get(role) != route for role, route in roles.items())
        _store_routes("custom" if differs or preset not in PRESET_IDS else preset, roles)
    elif preset == "custom":
        _store_routes("custom", {})
    return get_routing()


def resolve(role: str) -> tuple[Provider, str]:
    """The provider and model for a role. Falls back to offline when the routed provider has no key."""
    if _provider_override is not None:
        return _provider_override, "override"
    route = get_routing().roles.get(role)
    if route is not None and route.provider != "offline":
        row = get_connection(route.provider)
        if row is not None and row.kind != "media" and is_usable(row):
            return build_provider(row), route.model
    return OfflineProvider(), OFFLINE_MODEL


def active_provider() -> str:
    """The provider that will write slides right now (reported by /health)."""
    return resolve("writer")[0].id


# ---------------------------------------------------------------- the agent entry point
async def complete(request: LLMRequest, output: type[T]) -> tuple[T, LLMResult]:
    """Run a structured request for the request's role and validate the answer against `output`."""
    provider, model = resolve(request.role)
    current = request
    problem = ""
    for _attempt in range(2):
        result = await with_retries(lambda: provider.complete(current, model))
        try:
            return output.model_validate(result.data), result
        except ValidationError as error:
            problem = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:5])
            if provider.id == "offline":
                break
            current = replace(request, prompt=f"{request.prompt}\n\nYour previous answer did not match the "
                                              f"required structure ({problem}). Answer again and follow it exactly.")
    raise LLMError(f"The model's answer did not match the expected structure ({problem}).")
