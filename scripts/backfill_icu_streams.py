import asyncio
import logging
import time
from server.database import get_db
from server.services.intervals_icu import fetch_activity_streams, is_configured
from server.services.sync import _extract_streams, _store_streams, _backfill_start_location
from server.metrics import process_ride_samples
from server.queries import get_latest_metric
from server.ingest import get_benchmark_for_date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def backfill_icu_streams():
    """Find ICU-synced rides missing stream data or metrics and fix them."""
    if not is_configured():
        logger.error("Intervals.icu is not configured. Set API key and Athlete ID in Settings.")
        return

    with get_db() as conn:
        # Find all ICU rides
        rides = conn.execute(
            "SELECT id, filename, date, duration_s, ftp FROM rides WHERE filename LIKE 'icu_%' ORDER BY date DESC"
        ).fetchall()

    logger.info(f"Found {len(rides)} ICU-synced rides to check.")

    for i, ride in enumerate(rides):
        ride_id = ride["id"]
        filename = ride["filename"]
        icu_id = filename.replace("icu_", "")
        ride_date = ride["date"]
        
        # Check if we already have records
        with get_db() as conn:
            row = conn.execute("SELECT count(*) as count FROM ride_records WHERE ride_id = %s", (ride_id,)).fetchone()
            record_count = row["count"]
            
            # Check if we have power bests
            row = conn.execute("SELECT count(*) as count FROM power_bests WHERE ride_id = %s", (ride_id,)).fetchone()
            pb_count = row["count"]
            
        # Re-process if missing either records OR power bests (for rides with power data)
        # We also re-process if power_bests count is low (should be 6)
        if record_count > 0 and pb_count >= 6:
            logger.info(f"Skipping ride {ride_date} ({filename}) - already has data.")
            continue
            
        logger.info(f"Processing ride {ride_date} ({filename}) - {record_count} records, {pb_count} power bests...")
        
        try:
            # Fetch streams
            streams = fetch_activity_streams(icu_id)
            if not streams:
                logger.warning(f"No streams found for {icu_id}")
                continue
                
            with get_db() as conn:
                # 1. Store streams if missing
                if record_count == 0:
                    # Clear old records just in case
                    conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
                    _store_streams(ride_id, streams, conn=conn)
                    _backfill_start_location(ride_id, streams, conn=conn)
                    
                # 2. Recalculate metrics
                stream_map = _extract_streams(streams)
                raw_powers = stream_map.get("watts", [])
                raw_hrs = stream_map.get("heartrate", [])
                raw_cadences = stream_map.get("cadence", [])
                
                lthr = get_latest_metric(conn, "lthr", ride_date)
                max_hr_setting = get_latest_metric(conn, "max_hr", ride_date)
                resting_hr = get_latest_metric(conn, "resting_hr", ride_date)
                
                ftp = get_benchmark_for_date(conn, "ftp", ride_date)
                if ftp <= 0:
                    ftp = ride["ftp"] or 0
                    
                metrics = process_ride_samples(
                    raw_powers,
                    raw_hrs,
                    raw_cadences,
                    ftp,
                    ride["duration_s"],
                    lthr=lthr,
                    max_hr=max_hr_setting,
                    resting_hr=resting_hr,
                )
                
                # 3. Update ride record
                if metrics["has_power_data"]:
                    pb_map = {pb["duration_s"]: pb["power"] for pb in metrics["power_bests"]}
                    conn.execute(
                        """UPDATE rides SET 
                           normalized_power = %s, tss = %s, intensity_factor = %s, variability_index = %s,
                           avg_power = %s, avg_hr = %s, avg_cadence = %s,
                           best_1min_power = %s, best_5min_power = %s, best_20min_power = %s, best_60min_power = %s,
                           has_power_data = TRUE, data_status = %s
                           WHERE id = %s""",
                        (
                            metrics["np_power"],
                            metrics["tss"],
                            metrics["intensity_factor"],
                            metrics["variability_index"],
                            metrics["avg_power"],
                            metrics["avg_hr"],
                            metrics["avg_cadence"],
                            pb_map.get(60),
                            pb_map.get(300),
                            pb_map.get(1200),
                            pb_map.get(3600),
                            metrics["data_status"],
                            ride_id,
                        ),
                    )
                else:
                    conn.execute(
                        "UPDATE rides SET avg_hr = %s, avg_cadence = %s WHERE id = %s",
                        (metrics["avg_hr"], metrics["avg_cadence"], ride_id)
                    )
                    if metrics["tss"] > 0:
                        conn.execute("UPDATE rides SET tss = %s WHERE id = %s", (metrics["tss"], ride_id))
                    
                # 4. Update power bests
                if metrics["power_bests"]:
                    # Delete old ones first
                    conn.execute("DELETE FROM power_bests WHERE ride_id = %s", (ride_id,))
                    # Insert new ones
                    conn.executemany(
                        "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        [
                            (
                                ride_id,
                                ride_date,
                                pb["duration_s"],
                                pb["power"],
                                pb.get("avg_hr"),
                                pb.get("avg_cadence"),
                                pb.get("start_offset_s"),
                            )
                            for pb in metrics["power_bests"]
                        ],
                    )
                
                conn.commit()
                logger.info(f"Successfully backfilled data for {ride_date}")
                
            # Rate limiting avoidance
            if i % 10 == 0:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}", exc_info=True)

    logger.info("Backfill complete.")

if __name__ == "__main__":
    asyncio.run(backfill_icu_streams())
