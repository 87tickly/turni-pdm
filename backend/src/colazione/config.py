"""Application configuration loaded from environment variables.

Vedi `docs/STACK-TECNICO.md` §6 per il modello completo di env vars.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tutte le impostazioni runtime, caricate da `.env.local` o env vars."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "colazione"
    log_level: str = "INFO"
    debug: bool = False

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg://colazione:colazione@localhost:5432/colazione",
        description="Postgres connection string (psycopg3 driver).",
    )

    # --- Auth (placeholder, popolato in Sprint 2) ---
    jwt_secret: str = Field(
        default="dev-secret-change-me-min-32-characters-long",
        description="Chiave firma JWT. Min 32 char in prod.",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_min: int = 4320  # 72h
    jwt_refresh_token_expire_days: int = 30

    # --- Admin bootstrap (popolato in Sprint 2) ---
    admin_default_username: str = "admin"
    admin_default_password: str = ""  # se vuota, viene generata random

    # --- CORS ---
    cors_allow_origins: str = "http://localhost:5173"

    # --- Multi-tenant default ---
    default_azienda: str = "trenord"

    # --- Sprint 7.10 MR α.5: API live arturo (vetture passive) ---
    live_arturo_api_url: str = Field(
        default="https://arturo-production.up.railway.app",
        description=(
            "Base URL per l'API live di ARTURO (project Railway "
            "ARTURO-live, service arturo). Esposta senza auth in MR α.5."
        ),
    )
    live_arturo_timeout_sec: float = Field(
        default=5.0,
        description="Timeout per chiamata HTTP a live.arturo (sec).",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Singleton cached settings instance."""
    return Settings()
