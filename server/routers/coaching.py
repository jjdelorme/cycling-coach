"""AI coaching chat and session endpoints."""

import uuid
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from server.auth import CurrentUser, require_read, require_write
from server.dependencies import get_client_tz
from server.models.schemas import (
    ChatRequest, ChatResponse, SessionSummary, SessionDetail, SessionMessage,
)
from server.database import get_db, get_all_settings, set_setting

router = APIRouter(prefix="/api/coaching", tags=["coaching"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request, user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    from server.coaching.agent import chat

    session_id = req.session_id or str(uuid.uuid4())

    from server.database import get_athlete_setting, set_athlete_setting
    tz_str = getattr(request.state, "client_tz_str", "UTC")
    if tz_str != "UTC" and get_athlete_setting("timezone") != tz_str:
        set_athlete_setting("timezone", tz_str)

    response = await chat(
        message=req.message,
        session_id=session_id,
        user=user,
        tz=tz,
    )

    return ChatResponse(response=response, session_id=session_id)


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(user: CurrentUser = Depends(require_read)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC"
        ).fetchall()

    return [
        SessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, user: CurrentUser = Depends(require_read)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")

        events = conn.execute(
            "SELECT author, role, content_text, timestamp FROM chat_events WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()

    return SessionDetail(
        session_id=row["session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        messages=[
            SessionMessage(
                author=e["author"],
                role=e["role"],
                content_text=e["content_text"],
                timestamp=e["timestamp"],
            )
            for e in events
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: CurrentUser = Depends(require_write)):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    return {"status": "deleted"}


@router.get("/settings")
async def get_settings(user: CurrentUser = Depends(require_read)):
    """Get all coach settings (athlete profile, principles, etc.)."""
    return get_all_settings()


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.put("/settings")
async def update_setting(req: SettingUpdate, user: CurrentUser = Depends(require_write)):
    """Update a single coach setting."""
    valid_keys = {"athlete_profile", "coaching_principles", "coach_role", "plan_management", "theme", "units", "intervals_icu_api_key", "intervals_icu_athlete_id", "gemini_model", "gcp_location", "gemini_api_key"}
    if req.key not in valid_keys:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid key. Must be one of: {', '.join(sorted(valid_keys))}")
    # Reset the cached agent/runner when AI settings change so new values take effect
    if req.key in ("gemini_model", "gcp_location", "gemini_api_key"):
        from server.coaching.agent import reset_runner
        reset_runner()
    set_setting(req.key, req.value)
    return {"status": "updated", "key": req.key}


@router.post("/settings/reset")
async def reset_settings(user: CurrentUser = Depends(require_write)):
    """Reset all coach settings to defaults."""
    with get_db() as conn:
        conn.execute("DELETE FROM coach_settings")
    return {"status": "reset"}
