-- 0007_ride_records_timestamp.sql
-- Promote ride_records.timestamp_utc from TEXT to TIMESTAMPTZ.
--
-- WHY: The timezone schema migration (0006) promoted rides.start_time to
-- TIMESTAMPTZ but missed ride_records.timestamp_utc. This column stores
-- per-second UTC timestamps from FIT file recordings. Promoting to
-- TIMESTAMPTZ enables proper timestamp arithmetic and type safety.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'ride_records' AND column_name = 'timestamp_utc'
      AND data_type = 'text'
  ) THEN
    -- Append '+00:00' to timestamps missing timezone info
    UPDATE ride_records
    SET timestamp_utc = timestamp_utc || '+00:00'
    WHERE timestamp_utc IS NOT NULL
      AND timestamp_utc NOT LIKE '%Z'
      AND timestamp_utc NOT LIKE '%+%'
      AND LENGTH(timestamp_utc) > 10
      AND timestamp_utc !~ '[+-]\d{2}:\d{2}$';

    -- Cast to TIMESTAMPTZ
    ALTER TABLE ride_records ALTER COLUMN timestamp_utc TYPE TIMESTAMPTZ
      USING timestamp_utc::TIMESTAMPTZ;
  END IF;
END $$;
