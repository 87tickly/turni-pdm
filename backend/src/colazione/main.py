"""FastAPI app entry point.

Sprint 0.1: skeleton minimo con /health endpoint.
Sprint 2: registra il router auth (`/api/auth/login`, `/api/auth/refresh`).
Le route corse/giri/turni arrivano in Sprint 4.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from colazione import __version__
from colazione.api import anagrafiche as anagrafiche_routes
from colazione.api import auth as auth_routes
from colazione.api import giri as giri_routes
from colazione.api import personale as personale_routes
from colazione.api import pianificatore_pdc as pianificatore_pdc_routes
from colazione.api import programmi as programmi_routes
from colazione.api import turni_pdc as turni_pdc_routes
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

    app.include_router(auth_routes.router)
    app.include_router(programmi_routes.router)
    app.include_router(giri_routes.router)
    app.include_router(giri_routes.giri_dettaglio_router)
    app.include_router(anagrafiche_routes.router)
    app.include_router(turni_pdc_routes.router)
    app.include_router(turni_pdc_routes.turni_pdc_router)
    app.include_router(pianificatore_pdc_routes.router)
    app.include_router(personale_routes.router)

    return app


app = create_app()
