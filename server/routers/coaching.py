"""AI coaching chat and session endpoints."""

import uuid
from fastapi import APIRouter

from server.models.schemas import (
    ChatRequest, ChatResponse, SessionSummary, SessionDetail, SessionMessage,
)
from server.database import get_db

router = APIRouter(prefix="/api/coaching", tags=["coaching"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    from server.coaching.agent import chat

    session_id = req.session_id or str(uuid.uuid4())

    response = await chat(
        message=req.message,
        session_id=session_id,
    )

    return ChatResponse(response=response, session_id=session_id)


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
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
async def get_session(session_id: str):
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
async def delete_session(session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_events WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    return {"status": "deleted"}
