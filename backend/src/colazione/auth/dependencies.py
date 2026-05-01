"""FastAPI dependencies per autenticazione e autorizzazione.

Pattern d'uso::

    from fastapi import Depends
    from colazione.auth.dependencies import get_current_user, require_role
    from colazione.schemas.security import CurrentUser

    @router.get("/me")
    async def read_me(user: CurrentUser = Depends(get_current_user)):
        return user

    @router.get("/giri", dependencies=[Depends(require_role("PIANIFICATORE_GIRO"))])
    async def list_giri(): ...

L'utente corrente è ricavato esclusivamente dal JWT access token: niente
roundtrip al DB ad ogni request. Conseguenza: se un utente è disattivato
o un ruolo è revocato, il cambio diventa effettivo solo all'access
token successivo (max 72h con la config attuale). Per MVP è accettabile.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from colazione.auth.tokens import (
    ACCESS_TOKEN_TYPE,
    InvalidTokenError,
    decode_token,
)
from colazione.schemas.security import CurrentUser

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Estrae e valida l'access token da `Authorization: Bearer <token>`."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="autenticazione richiesta",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials, expected_type=ACCESS_TOKEN_TYPE)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        user_id=int(payload["sub"]),
        username=payload["username"],
        is_admin=bool(payload.get("is_admin", False)),
        roles=list(payload.get("roles", [])),
        azienda_id=int(payload["azienda_id"]),
    )


def require_role(role: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Factory: ritorna una dependency che richiede `role` (o admin)."""

    async def _checker(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.is_admin or role in user.roles:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"ruolo '{role}' richiesto",
        )

    return _checker


def require_any_role(*roles: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Factory: dependency che richiede uno qualsiasi dei ruoli forniti
    (admin bypassa).

    Usato per endpoint accessibili in sola lettura da più ruoli (es.
    GET /api/giri leggibile sia da PIANIFICATORE_GIRO sia da
    PIANIFICATORE_PDC). La scrittura resta protetta da `require_role`
    sul ruolo specifico.
    """
    if not roles:
        raise ValueError("require_any_role: serve almeno un ruolo")

    async def _checker(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.is_admin or any(r in user.roles for r in roles):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"uno dei ruoli {sorted(roles)} richiesto",
        )

    return _checker


def require_admin() -> Callable[..., Awaitable[CurrentUser]]:
    """Factory: dependency che richiede flag `is_admin=True`."""

    async def _checker(
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if user.is_admin:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin richiesto",
        )

    return _checker
