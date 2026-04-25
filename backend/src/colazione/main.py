"""FastAPI app entry point.

Sprint 0.1: skeleton minimo con /health endpoint.
Le route reali (corse, giri, turni_pdc, ...) arrivano in Sprint 4.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from colazione import __version__
from colazione.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks. In Sprint 1 si aggancia DB + Alembic upgrade."""
    settings = get_settings()
    app.state.settings = settings
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Colazione API",
        description="Programma di pianificazione ferroviaria nativa",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness probe. Sprint 0.1 minimal."""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
