-- 0004_rides_add_date_column.sql
-- Fix: add the `date` column to `rides` if it was created before the baseline
-- migration. The baseline uses CREATE TABLE IF NOT EXISTS, which is a no-op
-- when the table already exists with an older schema missing this column.

ALTER TABLE rides ADD COLUMN IF NOT EXISTS date TEXT;

-- Backfill date from start_time for any existing rows that have it
UPDATE rides SET date = TO_CHAR(start_time, 'YYYY-MM-DD')
  WHERE date IS NULL AND start_time IS NOT NULL;

-- Create the index if missing
CREATE INDEX IF NOT EXISTS idx_rides_date ON rides(date);
