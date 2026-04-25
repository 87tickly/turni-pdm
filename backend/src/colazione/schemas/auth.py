"""Schemas Pydantic — Strato 5 (auth + audit).

Schemi `Read` per utenti applicativi, ruoli, notifiche e audit log.
Vedi `models/auth.py`.

Nota: `password_hash` non è incluso in `AppUserRead` per non leakare
hash bcrypt in API responses. Quando servirà l'autenticazione (Sprint 2),
si aggiungeranno schemi `LoginRequest`, `TokenResponse`, ecc. in un
modulo dedicato `schemas/security.py`.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AppUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    persona_id: int | None = None
    azienda_id: int
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class AppUserRuoloRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_user_id: int
    ruolo: str


class NotificaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    destinatario_user_id: int
    tipo: str
    titolo: str
    payload_json: dict[str, Any]
    is_letta: bool
    letta_at: datetime | None = None
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: int | None = None
    azione: str
    target_tipo: str | None = None
    target_id: int | None = None
    payload_json: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime
