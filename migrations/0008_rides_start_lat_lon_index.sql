-- 0008_rides_start_lat_lon_index.sql
-- Composite partial index to speed up the bounding-box prefilter used by the
-- new "rides near a place" search (?near=&radius_km=) and by the existing
-- /api/analysis/route-matches endpoint. Partial-on-NOT-NULL keeps the index
-- small because indoor/virtual rides have no GPS.
CREATE INDEX IF NOT EXISTS idx_rides_start_lat_lon
    ON rides (start_lat, start_lon)
    WHERE start_lat IS NOT NULL;
