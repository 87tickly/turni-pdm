"""Modulo autenticazione (Sprint 2).

Composto da:
- `password.py` — hash bcrypt + verify
- `tokens.py` — JWT encode/decode (access + refresh)
- `dependencies.py` — FastAPI deps `get_current_user` + `require_role`

Le route HTTP sono in `colazione/api/auth.py`. Schemas I/O API in
`colazione/schemas/security.py`.
"""

from colazione.auth.dependencies import (
    get_current_user,
    require_admin,
    require_role,
)
from colazione.auth.password import hash_password, verify_password
from colazione.auth.tokens import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)

__all__ = [
    "ACCESS_TOKEN_TYPE",
    "REFRESH_TOKEN_TYPE",
    "InvalidTokenError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "hash_password",
    "require_admin",
    "require_role",
    "verify_password",
]
