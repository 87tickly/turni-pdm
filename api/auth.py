"""
Router autenticazione: register, login, me, admin endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.deps import get_db, get_current_user, hash_password, verify_password, create_token

router = APIRouter()


# ── Request models ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ── Endpoints ───────────────────────────────────────────────────

@router.post("/api/register")
def register(req: RegisterRequest):
    if len(req.username.strip()) < 3:
        raise HTTPException(400, "Username deve avere almeno 3 caratteri")
    if len(req.password) < 6:
        raise HTTPException(400, "Password deve avere almeno 6 caratteri")
    db = get_db()
    try:
        if db.get_user_by_username(req.username.strip()):
            raise HTTPException(400, "Username gia' in uso")
        pw_hash = hash_password(req.password)
        user_id = db.create_user(req.username.strip(), pw_hash, is_admin=False)
        token = create_token(user_id, req.username.strip(), False)
        return {
            "token": token,
            "user": {"id": user_id, "username": req.username.strip(), "is_admin": False},
        }
    finally:
        db.close()


@router.post("/api/login")
def login(req: LoginRequest):
    db = get_db()
    try:
        user = db.get_user_by_username(req.username.strip())
        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(401, "Credenziali non valide")
        db.update_last_login(user["id"])
        token = create_token(user["id"], user["username"], bool(user["is_admin"]))
        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "is_admin": bool(user["is_admin"]),
            },
        }
    finally:
        db.close()


@router.get("/api/me")
def get_me(user: dict = Depends(get_current_user)):
    return user


@router.get("/api/admin/users")
def admin_list_users(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        return {"users": db.get_all_users()}
    finally:
        db.close()


@router.get("/api/admin/saved-shifts")
def admin_all_saved_shifts(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        shifts = db.get_saved_shifts(user_id=None)
        users = {u["id"]: u["username"] for u in db.get_all_users()}
        for s in shifts:
            s["owner"] = users.get(s.get("user_id"), "\u2014")
        return {"shifts": shifts, "count": len(shifts)}
    finally:
        db.close()


@router.get("/api/admin/weekly-shifts")
def admin_all_weekly_shifts(user: dict = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(403, "Solo admin")
    db = get_db()
    try:
        shifts = db.get_weekly_shifts(user_id=None)
        users = {u["id"]: u["username"] for u in db.get_all_users()}
        for s in shifts:
            s["owner"] = users.get(s.get("user_id"), "\u2014")
        return {"shifts": shifts}
    finally:
        db.close()
