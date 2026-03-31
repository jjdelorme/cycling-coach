
import os
import logging
from server.database import get_db, init_db
from server.ingest import ingest_rides, compute_daily_pmc, backfill_hr_tss, backfill_laps, seed_periodization

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recompute():
    logger.info("Starting full re-ingestion for v1.5.2...")
    
    # Initialize DB schema
    init_db()
    
    # 1. Truncate existing ride data in a separate transaction
    with get_db() as conn:
        logger.info("Truncating existing ride tables...")
        conn.execute("TRUNCATE TABLE ride_records CASCADE")
        conn.execute("TRUNCATE TABLE ride_laps CASCADE")
        conn.execute("TRUNCATE TABLE power_bests CASCADE")
        conn.execute("DELETE FROM rides")
        conn.execute("TRUNCATE TABLE daily_metrics")
        conn.execute("TRUNCATE TABLE athlete_settings RESTART IDENTITY")
    
    with get_db() as conn:
        # 2. Re-ingest all rides (NO LIMIT on records)
        logger.info("Re-ingesting all rides from oldest to newest...")
        count = ingest_rides(conn)
        logger.info(f"Ingested {count} rides.")
        
        # 3. Backfill
        backfill_hr_tss(conn)
        
        # 4. Recompute PMC
        logger.info("Recomputing daily PMC...")
        compute_daily_pmc(conn)
        
        seed_periodization(conn)
        
        logger.info("Full re-ingestion and recomputation complete.")

if __name__ == "__main__":
    recompute()
