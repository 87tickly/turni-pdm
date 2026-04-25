"""Test JWT encode/decode (Sprint 2.1)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from colazione.auth.tokens import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from colazione.config import get_settings


def test_access_token_roundtrip() -> None:
    token = create_access_token(
        user_id=42,
        username="admin",
        is_admin=True,
        roles=["ADMIN"],
        azienda_id=1,
    )
    payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert payload["username"] == "admin"
    assert payload["is_admin"] is True
    assert payload["roles"] == ["ADMIN"]
    assert payload["azienda_id"] == 1


def test_refresh_token_roundtrip() -> None:
    token = create_refresh_token(user_id=42)
    payload = decode_token(token, expected_type=REFRESH_TOKEN_TYPE)
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"
    # Refresh non porta roles/username
    assert "roles" not in payload
    assert "username" not in payload


def test_decode_rejects_wrong_token_type() -> None:
    """Access token usato come refresh → InvalidTokenError."""
    access = create_access_token(user_id=1, username="x", is_admin=False, roles=[], azienda_id=1)
    with pytest.raises(InvalidTokenError, match="token type errato"):
        decode_token(access, expected_type=REFRESH_TOKEN_TYPE)


def test_decode_rejects_expired_token() -> None:
    settings = get_settings()
    expired_payload = {
        "sub": "1",
        "type": ACCESS_TOKEN_TYPE,
        "iat": int((datetime.now(UTC) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp()),
        "username": "x",
        "is_admin": False,
        "roles": [],
        "azienda_id": 1,
    }
    expired = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError, match="scaduto"):
        decode_token(expired, expected_type=ACCESS_TOKEN_TYPE)


def test_decode_rejects_bad_signature() -> None:
    """Token firmato con secret diverso → InvalidTokenError."""
    bad = jwt.encode(
        {"sub": "1", "type": ACCESS_TOKEN_TYPE},
        "different-secret-altogether-very-long",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(bad, expected_type=ACCESS_TOKEN_TYPE)


def test_decode_rejects_garbage() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-jwt-at-all", expected_type=ACCESS_TOKEN_TYPE)
