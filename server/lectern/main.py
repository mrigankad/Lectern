"""App factory. Run with: uv run uvicorn lectern.main:app --port 8000"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, store
from .agents.pipeline import pipeline, recover
from .db import init_db
from .llm import router as llm
from .llm.base import LLMError
from .media import router as media_router
from .mcp import mount as mount_mcp
from .mcp import setup as mcp_setup
from .routers import ask, critic, decks, export, layouts, media, settings, slides
from .routers import interview as interview_router
from .routers import shares as shares_router
from .routers import sources as sources_router
from .routers import brand as brand_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    llm.seed_defaults()
    media_router.seed_defaults()
    recover()
    manager = getattr(_app.state, "mcp_sessions", None)
    if manager is None:
        yield
    else:
        async with manager.run():
            yield
    await pipeline.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Lectern", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])

    @app.exception_handler(store.NotFound)
    async def _not_found(_request: Request, error: store.NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(store.Conflict)
    async def _conflict(_request: Request, error: store.Conflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(LLMError)
    async def _provider(_request: Request, error: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, error: RequestValidationError) -> JSONResponse:
        problems = []
        for item in error.errors()[:3]:
            where = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
            problems.append(f"{where}: {item.get('msg', 'is not valid')}" if where else str(item.get("msg")))
        return JSONResponse(status_code=422, content={
            "detail": "The request is not valid. " + "; ".join(problems) if problems else "The request is not valid."})

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "provider": llm.active_provider()}

    app.include_router(brand_router.router, prefix="/api")  # brand kits (U09)
    for module in (decks, slides, ask, critic, export, settings, layouts, media):
        app.include_router(module.router, prefix="/api")
    for extra in (interview_router, shares_router, sources_router):
        app.include_router(extra.router, prefix="/api")
    app.include_router(mcp_setup.router, prefix="/api")
    app.state.mcp_sessions = mount_mcp(app)   # MCP over streamable HTTP at /mcp
    return app


app = create_app()
