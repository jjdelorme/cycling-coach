"""Google OAuth token verification and role-based access control."""

from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from server.config import GOOGLE_CLIENT_ID, GOOGLE_AUTH_ENABLED
from server.database import get_db


@dataclass
class CurrentUser:
    email: str
    display_name: str
    avatar_url: str
    role: str  # 'none', 'read', 'readwrite', 'admin'


def verify_google_token(token: str) -> dict:
    """Verify a Google ID token and return its claims."""
    try:
        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        return claims
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def _upsert_user(email: str, display_name: str, avatar_url: str) -> str:
    """Upsert user record and return their role."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT role FROM users WHERE email = %s", (email,)
        ).fetchone()

        if row:
            conn.execute(
                "UPDATE users SET display_name = %s, avatar_url = %s, last_login = CURRENT_TIMESTAMP WHERE email = %s",
                (display_name, avatar_url, email),
            )
            return row["role"]
        else:
            conn.execute(
                "INSERT INTO users (email, display_name, avatar_url, role, last_login) VALUES (%s, %s, %s, 'none', CURRENT_TIMESTAMP)",
                (email, display_name, avatar_url),
            )
            return "none"


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency: extract and verify the Google ID token, return CurrentUser."""
    if not GOOGLE_AUTH_ENABLED:
        return CurrentUser(
            email="dev@localhost",
            display_name="Dev User",
            avatar_url="",
            role="admin",
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth_header[7:]
    claims = verify_google_token(token)

    email = claims.get("email", "")
    display_name = claims.get("name", "")
    avatar_url = claims.get("picture", "")

    role = _upsert_user(email, display_name, avatar_url)

    return CurrentUser(
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        role=role,
    )


def require_read(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in ("read", "readwrite", "admin"):
        raise HTTPException(status_code=403, detail="Read access required")
    return user


def require_write(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role not in ("readwrite", "admin"):
        raise HTTPException(status_code=403, detail="Write access required")
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
