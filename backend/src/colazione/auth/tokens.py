"""JWT encoding/decoding.

Due token type: `access` (corto, autorizza le request) e `refresh`
(lungo, scambia per un nuovo access). Algoritmo HS256 simmetrico.

Claims comuni:
- `sub` (str): user_id come stringa
- `type` (str): "access" oppure "refresh"
- `iat` (int): issued-at timestamp UTC
- `exp` (int): expiry timestamp UTC

Solo nei token "access":
- `username` (str)
- `is_admin` (bool)
- `roles` (list[str]): ruoli applicativi (vedi `app_user_ruolo`)
- `azienda_id` (int): tenant
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from colazione.config import get_settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class InvalidTokenError(Exception):
    """Token JWT malformato, scaduto, o di tipo sbagliato."""


def _now_utc() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    *,
    user_id: int,
    username: str,
    is_admin: bool,
    roles: list[str],
    azienda_id: int,
) -> str:
    """Genera un access token con claims completi (auth + autorizzazione)."""
    settings = get_settings()
    now = _now_utc()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_expire_min)).timestamp()),
        "username": username,
        "is_admin": is_admin,
        "roles": roles,
        "azienda_id": azienda_id,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(*, user_id: int) -> str:
    """Genera un refresh token con claim minimi.

    Il refresh token NON contiene roles/is_admin: per riemettere un
    access valido, il sistema rilegge questi dati dal DB al refresh.
    """
    settings = get_settings()
    now = _now_utc()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": REFRESH_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_token_expire_days)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    """Decodifica e valida un token JWT.

    Solleva `InvalidTokenError` se la firma non valida, il token è
    scaduto, o il claim `type` non matcha `expected_type`.
    """
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidTokenError("token scaduto") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"token non valido: {exc}") from exc

    actual_type = payload.get("type")
    if actual_type != expected_type:
        raise InvalidTokenError(
            f"token type errato: atteso '{expected_type}', ricevuto '{actual_type}'"
        )

    return payload
