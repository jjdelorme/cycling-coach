-- Migration: Add session_type column to chat_sessions
--
-- The chat_sessions table is shared by the coaching and nutrition agents.
-- Previously, the nutrition router used a fragile `session_id LIKE 'nutrition-%'`
-- filter to distinguish sessions, which never worked because session IDs were
-- plain UUIDs. This migration adds a proper session_type column and backfills
-- existing nutrition sessions by checking chat_events.author.
--
-- Safe to run on production — all statements are idempotent.
--
-- Usage:
--   psql $DATABASE_URL -f scripts/migrate_chat_session_type.sql
--   # or against the local dev DB:
--   psql -h localhost -U postgres -d postgres -f scripts/migrate_chat_session_type.sql

BEGIN;

-- 1. Add the session_type column (existing rows default to 'coaching')
ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS session_type TEXT NOT NULL DEFAULT 'coaching';

-- 2. Backfill: tag sessions that contain nutritionist messages
UPDATE chat_sessions
   SET session_type = 'nutrition'
 WHERE session_type = 'coaching'
   AND session_id IN (
       SELECT DISTINCT session_id FROM chat_events WHERE author = 'nutritionist'
   );

-- 3. Index for filtered queries on session_type
CREATE INDEX IF NOT EXISTS idx_chat_sessions_type ON chat_sessions(session_type);

COMMIT;

-- Verify after running:
-- SELECT session_type, COUNT(*) FROM chat_sessions GROUP BY session_type;
