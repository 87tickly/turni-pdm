"""
Dipendenze condivise per i router API: database, autenticazione JWT.
"""

import os
from datetime import datetime, timedelta

import bcrypt
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.database.db import Database

# ---------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------
DB_PATH = "turni.db"


def get_db() -> Database:
    return Database(db_path=DB_PATH)


# ---------------------------------------------------------------
# AUTH (JWT)
# ---------------------------------------------------------------
_jwt_secret_env = os.environ.get("JWT_SECRET")
if not _jwt_secret_env and os.environ.get("DATABASE_URL"):
    raise RuntimeError(
        "JWT_SECRET env var obbligatoria in produzione (DATABASE_URL impostata). "
        "Imposta JWT_SECRET prima di avviare il server."
    )
SECRET_KEY = _jwt_secret_env or "dev-secret-turni-pdm-local-only"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not credentials:
        raise HTTPException(401, "Token mancante")
    try:
        payload = jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
        return {
            "id": int(payload["sub"]),
            "username": payload["username"],
            "is_admin": payload.get("is_admin", False),
        }
    except JWTError:
        raise HTTPException(401, "Token non valido o scaduto")
