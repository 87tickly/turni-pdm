"""Route HTTP per autenticazione (Sprint 2).

- POST /api/auth/login  → emette access + refresh token
- POST /api/auth/refresh → riemette access da refresh

Per `get_current_user` e `require_role` vedi `colazione/auth/dependencies.py`.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from colazione.auth import (
    REFRESH_TOKEN_TYPE,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from colazione.config import get_settings
from colazione.db import get_session
from colazione.models.auth import AppUser, AppUserRuolo
from colazione.schemas.security import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _load_roles(session: AsyncSession, app_user_id: int) -> list[str]:
    stmt = select(AppUserRuolo.ruolo).where(AppUserRuolo.app_user_id == app_user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()

    stmt = select(AppUser).where(AppUser.username == req.username)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="credenziali non valide",
        )

    roles = await _load_roles(session, user.id)

    user.last_login_at = datetime.now(UTC)
    await session.commit()

    access = create_access_token(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        roles=roles,
        azienda_id=user.azienda_id,
    )
    refresh = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in_min=settings.jwt_access_token_expire_min,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    req: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    settings = get_settings()

    try:
        payload = decode_token(req.refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = int(payload["sub"])
    user = await session.get(AppUser, user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="utente non valido o disattivato",
        )

    roles = await _load_roles(session, user.id)
    access = create_access_token(
        user_id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        roles=roles,
        azienda_id=user.azienda_id,
    )

    return RefreshResponse(
        access_token=access,
        expires_in_min=settings.jwt_access_token_expire_min,
    )


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Identità dell'utente corrente, derivata dal JWT access token."""
    return user
