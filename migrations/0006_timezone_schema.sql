-- 0006_timezone_schema.sql
-- Timezone schema migration: normalize timestamps and promote TEXT date
-- columns to native PostgreSQL DATE / TIMESTAMPTZ types.
--
-- WHY: The application is migrating to timezone-aware date handling. All ride
-- queries now derive local dates at query time using
--     (start_time AT TIME ZONE :tz)::DATE
-- This requires start_time to be TIMESTAMPTZ (not TEXT). The rides.date
-- column is no longer read by any query (Phase 2 completed) and can be
-- dropped. Other TEXT date columns (daily_metrics, planned_workouts, etc.)
-- are promoted to native DATE for correctness and query performance.
--
-- PREREQUISITES:
--   - All application code has been updated to stop reading rides.date
--   - All INSERT paths no longer write rides.date
--   - All queries use AT TIME ZONE pattern instead of rides.date

-- ---------------------------------------------------------------------------
-- Step 1: Fix non-UTC start_time values from legacy intervals.icu syncs
-- ---------------------------------------------------------------------------
-- Legacy syncs stored start_date_local (local time, no timezone suffix).
-- FIT-ingested rides store UTC but also without a suffix (e.g., "2026-04-09T03:30:00").
-- Append '+00:00' to timestamps missing timezone info so the TIMESTAMPTZ cast
-- treats them as UTC (best-effort approximation for historical data).
--
-- We use a regex to precisely identify timestamps that already carry a
-- timezone offset (ending in +NN:NN or -NN:NN or Z), and skip those.
UPDATE rides
SET start_time = start_time || '+00:00'
WHERE start_time IS NOT NULL
  AND start_time NOT LIKE '%Z'
  AND start_time NOT LIKE '%+%'
  AND LENGTH(start_time) > 10
  AND start_time !~ '[+-]\d{2}:\d{2}$';

-- ---------------------------------------------------------------------------
-- Step 2: Promote start_time TEXT -> TIMESTAMPTZ
-- ---------------------------------------------------------------------------
-- After Step 1, every start_time value is a valid ISO8601 string with
-- timezone info. The cast is now safe.
ALTER TABLE rides ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- Step 3: Drop the now-unused rides.date column
-- ---------------------------------------------------------------------------
-- All queries derive local dates from start_time AT TIME ZONE. No code reads
-- or writes rides.date anymore.
ALTER TABLE rides DROP COLUMN IF EXISTS date;

-- ---------------------------------------------------------------------------
-- Step 4: Promote other TEXT date columns to native DATE type
-- ---------------------------------------------------------------------------
-- These columns store YYYY-MM-DD strings and benefit from proper DATE type
-- for comparison operators, indexing, and type safety.
ALTER TABLE daily_metrics ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE planned_workouts ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN start_date TYPE DATE USING start_date::DATE;
ALTER TABLE periodization_phases ALTER COLUMN end_date TYPE DATE USING end_date::DATE;
ALTER TABLE power_bests ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE athlete_settings ALTER COLUMN date_set TYPE DATE USING date_set::DATE;

-- Promote meal-related TEXT date columns to DATE as well.
-- These store YYYY-MM-DD calendar dates for meal plans and logs.
ALTER TABLE planned_meals ALTER COLUMN date TYPE DATE USING date::DATE;
ALTER TABLE meal_logs ALTER COLUMN date TYPE DATE USING date::DATE;

-- ---------------------------------------------------------------------------
-- Step 5: Update indexes
-- ---------------------------------------------------------------------------
-- Add index on start_time for timezone-aware date queries.
CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time);

-- Drop the orphaned index that referenced the now-dropped rides(date) column.
DROP INDEX IF EXISTS idx_rides_date;
