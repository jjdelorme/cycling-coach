"""Database-backed session service for persistent chat history."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from google.adk.sessions import Session, BaseSessionService
from google.adk.sessions.base_session_service import ListSessionsResponse, GetSessionConfig
from google.adk.events import Event
from google.genai import types

from server.database import get_db


class DbSessionService(BaseSessionService):
    """Persists chat sessions and events to PostgreSQL."""

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = session_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session_type = "nutrition" if app_name == "nutrition-coach" else "coaching"

        with get_db() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (session_id, user_id, session_type, title, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (session_id) DO NOTHING",
                (sid, user_id, session_type, "New conversation", now, now),
            )

        return Session(
            app_name=app_name,
            user_id=user_id,
            id=sid,
            state=state or {},
            events=[],
        )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE session_id = %s", (session_id,)
            ).fetchone()

            if not row:
                return None

            events_rows = conn.execute(
                "SELECT * FROM chat_events WHERE session_id = %s ORDER BY id",
                (session_id,),
            ).fetchall()

        events = []
        for er in events_rows:
            content = types.Content(
                role=er["role"] or "user",
                parts=[types.Part.from_text(text=er["content_text"])] if er["content_text"] else [],
            )
            events.append(Event(
                author=er["author"] or "user",
                content=content,
            ))

        return Session(
            app_name=app_name,
            user_id=user_id,
            id=session_id,
            state={},
            events=events,
        )

    async def list_sessions(
        self, *, app_name: str, user_id: Optional[str] = None
    ) -> ListSessionsResponse:
        with get_db() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM chat_sessions WHERE user_id = %s ORDER BY updated_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chat_sessions ORDER BY updated_at DESC"
                ).fetchall()

        sessions = []
        for row in rows:
            sessions.append(Session(
                app_name=app_name,
                user_id=row["user_id"],
                id=row["session_id"],
                state={},
                events=[],
            ))

        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        with get_db() as conn:
            conn.execute("DELETE FROM chat_events WHERE session_id = %s", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))

    async def append_event(self, session: Session, event: Event) -> Event:
        event = await super().append_event(session, event)

        # Persist the event
        if event.content and event.content.parts:
            text_parts = [p.text for p in event.content.parts if p.text]
            if text_parts:
                content_text = "\n".join(text_parts)
                now = datetime.now(timezone.utc).isoformat()
                role = event.content.role if event.content else "user"

                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO chat_events (session_id, author, role, content_text, timestamp) VALUES (%s, %s, %s, %s, %s)",
                        (session.id, event.author, role, content_text, now),
                    )
                    # Update session title from first user message if still default
                    if role == "user":
                        conn.execute(
                            "UPDATE chat_sessions SET updated_at = %s, title = CASE WHEN title = 'New conversation' THEN %s ELSE title END WHERE session_id = %s",
                            (now, content_text[:80], session.id),
                        )
                    else:
                        conn.execute(
                            "UPDATE chat_sessions SET updated_at = %s WHERE session_id = %s",
                            (now, session.id),
                        )

        return event
