
import os
import logging
from server.database import get_db, init_db, set_athlete_setting
from server.ingest import ingest_rides, compute_daily_pmc, backfill_hr_tss, backfill_laps, seed_periodization

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recompute():
    logger.info("Starting full re-ingestion for v1.5.2...")
    
    # Initialize DB schema
    init_db()
    
    # 1. Establishment of TRUTH benchmarks before ingestion
    with get_db() as conn:
        logger.info("Setting manual overrides for benchmarks...")
        # Clear existing bogus settings
        conn.execute("TRUNCATE TABLE athlete_settings RESTART IDENTITY")
        
        # Set the real history as described
        set_athlete_setting('ftp', '261', '2025-01-01') # Historical base
        set_athlete_setting('ftp', '270', '2026-03-28') # Recent update
        set_athlete_setting('weight_kg', '79.4', '2025-01-01') # Historical base
        set_athlete_setting('weight_kg', '77.1', '2026-03-28') # Recent update
        
        # Truncate existing ride data
        logger.info("Truncating existing ride tables...")
        conn.execute("TRUNCATE TABLE ride_records CASCADE")
        conn.execute("TRUNCATE TABLE ride_laps CASCADE")
        conn.execute("TRUNCATE TABLE power_bests CASCADE")
        conn.execute("DELETE FROM rides")
        conn.execute("TRUNCATE TABLE daily_metrics")
    
    with get_db() as conn:
        # 2. Re-ingest all rides (now with NO LIMIT on records)
        logger.info("Re-ingesting all rides from oldest to newest...")
        count = ingest_rides(conn)
        logger.info(f"Ingested {count} rides.")
        
        # 3. Backfill
        backfill_hr_tss(conn)
        
        # 4. Recompute PMC (which will now correctly prioritize your March 28 update)
        logger.info("Recomputing daily PMC with priority benchmarks...")
        compute_daily_pmc(conn)
        
        seed_periodization(conn)
        
        logger.info("Full re-ingestion and recomputation complete.")

if __name__ == "__main__":
    recompute()
