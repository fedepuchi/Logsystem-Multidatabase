from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import connections as connections_api
from app.api import logs as logs_api
from app.api import sources as sources_api
from app.config import get_settings
from app.metadata.db import close_metadata_db, init_metadata_db
from app.storage.router import storage_router

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_static_dir() -> Optional[Path]:
    """Localiza el build del frontend.

    Se prueba STATIC_DIR primero, después la ruta del repo (útil en `make dev`)
    y por último la ruta dentro de la imagen Docker, donde PROJECT_ROOT apunta
    a `/` y la heurística relativa no sirve.
    """

    settings = get_settings()

    candidates = []
    if settings.static_dir:
        candidates.append(Path(settings.static_dir))
    candidates.append(PROJECT_ROOT / "frontend" / "dist")
    candidates.append(Path("/app/frontend/dist"))

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    await init_metadata_db(settings.sqlite_path)
    logger.info("metadata inicializada en %s", settings.sqlite_path)

    await storage_router.rebuild()
    logger.info("router reconstruido desde la metadata")

    yield

    await storage_router.close_all()
    await close_metadata_db()
    logger.info("shutdown completo")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="LogMon - Monitoreo de Logs Multi Base de Datos",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(logs_api.router)
    app.include_router(connections_api.router)
    app.include_router(sources_api.router)

    static_dir = _resolve_static_dir()
    if static_dir is None:
        logger.warning(
            "No se encontro el build del frontend; se sirve solo la API. "
            "Ejecuta `vite build` en logmon/frontend para generar dist/."
        )
        return app

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = static_dir / "index.html"
    static_root = static_dir.resolve()

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Sin esta guarda el catch-all devolvería index.html con 200 para
        # cualquier ruta de API inexistente, escondiendo los 404 reales.
        if full_path == "health" or full_path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

        candidate = (static_root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(static_root):
            return FileResponse(candidate)
        return FileResponse(index_file)

    logger.info("SPA servida desde %s", static_dir)
    return app


app = create_app()
