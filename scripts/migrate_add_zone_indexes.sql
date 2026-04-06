-- Migration: Add performance indexes for zone distribution query
--
-- The /api/analysis/zones endpoint does a full scan of ride_records joined to rides
-- to compute power zone distribution. On large datasets (200K+ rows), this consistently
-- runs 2.5–3.2 seconds and triggers slow-query warnings.
--
-- These two indexes eliminate the full-scan and allow the planner to push the date
-- filter down before joining ride_records, making the common filtered query fast.
--
-- Safe to run on production — both are CREATE INDEX IF NOT EXISTS (idempotent).
-- On large datasets, consider running during a low-traffic window as index creation
-- will briefly lock ride_records for writes.
--
-- Usage:
--   psql $DATABASE_URL -f scripts/migrate_add_zone_indexes.sql
--   # or against the local dev DB:
--   psql -h localhost -U postgres -d postgres -f scripts/migrate_add_zone_indexes.sql

-- 1. Composite index on ride_records(ride_id, power)
--    Enables index-only scans when grouping/filtering power by ride.
CREATE INDEX IF NOT EXISTS idx_ride_records_ride_id_power
    ON ride_records(ride_id, power);

-- 2. Index on rides(date)
--    Allows the planner to apply date range filters on rides before joining ride_records.
CREATE INDEX IF NOT EXISTS idx_rides_date
    ON rides(date);

-- Verify the indexes exist after running:
-- SELECT indexname, tablename FROM pg_indexes
-- WHERE indexname IN ('idx_ride_records_ride_id_power', 'idx_rides_date');
