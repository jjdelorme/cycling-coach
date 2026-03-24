"""SQLite-backed memory service for persistent coach memory."""

import re
from datetime import datetime, timezone
from typing import Optional

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types

from server.database import get_db


def _extract_words_lower(text: str) -> set[str]:
    return set(word.lower() for word in re.findall(r'[A-Za-z]+', text))


class SqliteMemoryService(BaseMemoryService):
    """Persists conversation memory to SQLite with keyword-based search."""

    async def add_session_to_memory(self, session: Session) -> None:
        if not session.events:
            return

        now = datetime.now(timezone.utc).isoformat()

        with get_db() as conn:
            for event in session.events:
                if not event.content or not event.content.parts:
                    continue
                text_parts = [p.text for p in event.content.parts if p.text]
                if not text_parts:
                    continue
                content_text = "\n".join(text_parts)
                author = event.author or "unknown"

                # Avoid duplicates: check if this exact text already exists for this session
                existing = conn.execute(
                    "SELECT id FROM coach_memory WHERE user_id = ? AND author = ? AND content_text = ?",
                    (session.user_id, author, content_text),
                ).fetchone()
                if existing:
                    continue

                conn.execute(
                    "INSERT INTO coach_memory (user_id, author, content_text, timestamp) VALUES (?, ?, ?, ?)",
                    (session.user_id, author, content_text, now),
                )

    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM coach_memory WHERE user_id = ? ORDER BY id DESC LIMIT 500",
                (user_id,),
            ).fetchall()

        words_in_query = _extract_words_lower(query)
        if not words_in_query:
            return SearchMemoryResponse()

        memories = []
        for row in rows:
            content_text = row["content_text"]
            words_in_memory = _extract_words_lower(content_text)
            if not words_in_memory:
                continue

            if any(qw in words_in_memory for qw in words_in_query):
                memories.append(MemoryEntry(
                    content=types.Content(
                        role="user" if row["author"] == "user" else "model",
                        parts=[types.Part.from_text(text=content_text)],
                    ),
                    author=row["author"],
                    timestamp=row["timestamp"],
                ))

        return SearchMemoryResponse(memories=memories)
