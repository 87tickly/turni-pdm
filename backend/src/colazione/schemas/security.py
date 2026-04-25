"""Schemas Pydantic — autenticazione e autorizzazione (Sprint 2).

Distinto da `schemas/auth.py` (strato 5 anagrafica utenti) perché qui
si tratta di shape I/O API per login/refresh, non di entità DB.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_min: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_min: int


class CurrentUser(BaseModel):
    """Identità autenticata derivata dal JWT access token corrente.

    Iniettato dalla dependency `get_current_user`. NON è un modello
    DB — è la versione "in flight" dell'utente per il request.
    """

    user_id: int
    username: str
    is_admin: bool
    roles: list[str]
    azienda_id: int
