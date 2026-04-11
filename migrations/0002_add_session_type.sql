-- 0002_add_session_type.sql
-- Add session_type column to chat_sessions to distinguish coaching vs nutrition sessions.

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS session_type TEXT NOT NULL DEFAULT 'coaching';

CREATE INDEX IF NOT EXISTS idx_chat_sessions_type ON chat_sessions(session_type);

-- Backfill: any session that has a nutritionist message is a nutrition session.
UPDATE chat_sessions SET session_type = 'nutrition'
  WHERE session_type = 'coaching'
    AND session_id IN (SELECT DISTINCT session_id FROM chat_events WHERE author = 'nutritionist');
