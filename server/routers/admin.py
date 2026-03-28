"""Admin user management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.auth import CurrentUser, get_current_user, require_admin, verify_google_token, create_app_token, _upsert_user
from server.database import get_db

router = APIRouter(prefix="/api", tags=["admin"])


# --- Auth ---

class LoginRequest(BaseModel):
    google_token: str


@router.post("/auth/login")
async def login(body: LoginRequest):
    """Exchange a Google ID token for a long-lived app session token."""
    claims = verify_google_token(body.google_token)
    email = claims.get("email", "")
    display_name = claims.get("name", "")
    avatar_url = claims.get("picture", "")

    role = _upsert_user(email, display_name, avatar_url)

    app_token = create_app_token(email, display_name, avatar_url)
    return {
        "token": app_token,
        "email": email,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "role": role,
    }


# --- Current user (any authenticated user) ---

@router.get("/users/me")
async def get_me(user: CurrentUser = Depends(get_current_user)):
    return {
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
    }


# --- Admin user management ---

@router.get("/admin/users")
async def list_users(user: CurrentUser = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT email, display_name, avatar_url, role, created_at, last_login FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


class UserCreate(BaseModel):
    email: str
    role: str = "read"


@router.post("/admin/users")
async def create_user(body: UserCreate, user: CurrentUser = Depends(require_admin)):
    if body.role not in ("none", "read", "readwrite", "admin"):
        raise HTTPException(status_code=400, detail="Role must be none, read, readwrite, or admin")

    with get_db() as conn:
        existing = conn.execute("SELECT email FROM users WHERE email = %s", (body.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        conn.execute(
            "INSERT INTO users (email, role) VALUES (%s, %s)",
            (body.email, body.role),
        )
    return {"status": "created", "email": body.email, "role": body.role}


class UserUpdate(BaseModel):
    role: str


@router.put("/admin/users/{email}")
async def update_user(email: str, body: UserUpdate, user: CurrentUser = Depends(require_admin)):
    if body.role not in ("none", "read", "readwrite", "admin"):
        raise HTTPException(status_code=400, detail="Role must be none, read, readwrite, or admin")
    if email == user.email:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    with get_db() as conn:
        existing = conn.execute("SELECT email FROM users WHERE email = %s", (email,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET role = %s WHERE email = %s", (body.role, email))
    return {"status": "updated", "email": email, "role": body.role}


@router.delete("/admin/users/{email}")
async def delete_user(email: str, user: CurrentUser = Depends(require_admin)):
    if email == user.email:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    with get_db() as conn:
        existing = conn.execute("SELECT email FROM users WHERE email = %s", (email,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("DELETE FROM users WHERE email = %s", (email,))
    return {"status": "deleted", "email": email}
