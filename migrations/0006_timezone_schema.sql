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
-- Step 1: Fix non-UTC start_time values and promote to TIMESTAMPTZ
-- ---------------------------------------------------------------------------
-- If start_time is still TEXT, fix timestamps missing timezone info, then cast.
-- If start_time is already TIMESTAMPTZ (e.g., from prior partial migration),
-- skip this step entirely.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'rides' AND column_name = 'start_time'
      AND data_type = 'text'
  ) THEN
    -- Append '+00:00' to timestamps missing timezone info (best-effort UTC)
    UPDATE rides
    SET start_time = start_time || '+00:00'
    WHERE start_time IS NOT NULL
      AND start_time NOT LIKE '%Z'
      AND start_time NOT LIKE '%+%'
      AND LENGTH(start_time) > 10
      AND start_time !~ '[+-]\d{2}:\d{2}$';

    -- Now safe to cast
    ALTER TABLE rides ALTER COLUMN start_time TYPE TIMESTAMPTZ USING start_time::TIMESTAMPTZ;
  END IF;
END $$;

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
-- Wrapped in DO block to skip columns that are already DATE type.
DO $$
DECLARE
  _tbl TEXT; _col TEXT;
BEGIN
  FOR _tbl, _col IN VALUES
    ('daily_metrics', 'date'),
    ('planned_workouts', 'date'),
    ('periodization_phases', 'start_date'),
    ('periodization_phases', 'end_date'),
    ('power_bests', 'date'),
    ('athlete_settings', 'date_set'),
    ('planned_meals', 'date'),
    ('meal_logs', 'date')
  LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name = _tbl AND column_name = _col
        AND data_type = 'text'
    ) THEN
      EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE DATE USING %I::DATE', _tbl, _col, _col);
    END IF;
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Step 5: Update indexes
-- ---------------------------------------------------------------------------
-- Add index on start_time for timezone-aware date queries.
CREATE INDEX IF NOT EXISTS idx_rides_start_time ON rides(start_time);

-- Drop the orphaned index that referenced the now-dropped rides(date) column.
DROP INDEX IF EXISTS idx_rides_date;
