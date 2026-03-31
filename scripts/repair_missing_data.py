import asyncio
import logging
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import get_db
from server.services.intervals_icu import fetch_activities, fetch_activity_streams, map_activity_to_ride, is_configured
from server.services.sync import _store_streams, _extract_streams, _backfill_start_location, _store_laps, map_intervals_to_laps, fetch_activity_intervals
from server.metrics import process_ride_samples
from server.queries import get_latest_metric
from server.ingest import get_benchmark_for_date, compute_daily_pmc

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def repair_missing_data():
    """Find rides missing records/bests and fetch them from Intervals.icu."""
    if not is_configured():
        logger.error("Intervals.icu not configured. Cannot repair.")
        return

    with get_db() as conn:
        # 1. Identify rides missing data
        # We check for rides that don't have power bests
        missing_rides = conn.execute("""
            SELECT id, date, distance_m, filename, duration_s, ftp, avg_hr, avg_cadence 
            FROM rides 
            WHERE id NOT IN (SELECT DISTINCT ride_id FROM power_bests)
            ORDER BY date DESC
        """).fetchall()

    if not missing_rides:
        logger.info("No rides found missing power bests.")
        return

    logger.info("Found %d rides missing detailed data. Attempting to match with Intervals.icu...", len(missing_rides))

    # 2. Fetch all Intervals.icu activities to build a map
    # We'll fetch the last 3 years to be safe
    oldest = (datetime.now().replace(year=datetime.now().year - 3)).strftime("%Y-%m-%d")
    activities = fetch_activities(oldest=oldest)
    
    # Map by (date, distance_rounded)
    icu_map = {}
    for act in activities:
        date = act.get("start_date_local", "")[:10]
        act_dist = act.get("distance")
        if act_dist is None:
            act_dist = 0
        dist = round(act_dist / 100) * 100
        icu_map[(date, dist)] = act

    repaired = 0
    failed = 0

    for i, ride in enumerate(missing_rides):
        ride_id = ride["id"]
        date = ride["date"]
        ride_dist_raw = ride["distance_m"]
        if ride_dist_raw is None:
            ride_dist_raw = 0
        dist = round(ride_dist_raw / 100) * 100
        filename = ride["filename"]
        
        logger.info("[%d/%d] Processing %s (%s, %.0fm)...", i+1, len(missing_rides), date, filename, ride["distance_m"])

        # Find match
        activity = None
        if filename.startswith("icu_"):
            icu_id = filename.replace("icu_", "")
            activity = next((a for a in activities if str(a.get("id")) == icu_id), None)
        else:
            activity = icu_map.get((date, dist))

        if not activity:
            logger.warning("  ! No matching Intervals.icu activity found for %s", date)
            failed += 1
            continue

        icu_id = activity.get("id")
        logger.info("  + Found match: ICU ID %s", icu_id)

        try:
            # Fetch streams
            streams = await asyncio.to_thread(fetch_activity_streams, icu_id)
            if not streams:
                logger.warning("  ! No streams found for ICU ID %s", icu_id)
                failed += 1
                continue

            with get_db() as conn:
                # Store streams
                _store_streams(ride_id, streams, conn=conn)
                _backfill_start_location(ride_id, streams, conn=conn)

                # Process samples
                stream_map = _extract_streams(streams)
                raw_powers = stream_map.get("watts", [])
                raw_hrs = stream_map.get("heartrate", [])
                raw_cadences = stream_map.get("cadence", [])

                lthr = get_latest_metric(conn, "lthr", date)
                max_hr = get_latest_metric(conn, "max_hr", date)
                resting_hr = get_latest_metric(conn, "resting_hr", date)
                ftp = get_benchmark_for_date(conn, "ftp", date)
                if ftp <= 0:
                    ftp = ride["ftp"] or 0

                metrics = await asyncio.to_thread(
                    process_ride_samples,
                    raw_powers, raw_hrs, raw_cadences,
                    ftp, ride["duration_s"],
                    lthr=lthr, max_hr=max_hr, resting_hr=resting_hr
                )

                # Persist metrics
                if metrics["has_power_data"]:
                    pb_map = {pb["duration_s"]: pb["power"] for pb in metrics["power_bests"]}
                    conn.execute(
                        """UPDATE rides SET 
                           normalized_power = %s, tss = %s, intensity_factor = %s, variability_index = %s,
                           avg_power = %s, avg_hr = %s, avg_cadence = %s,
                           best_1min_power = %s, best_5min_power = %s, best_20min_power = %s, best_60min_power = %s,
                           has_power_data = TRUE, data_status = 'cleaned'
                           WHERE id = %s""",
                        (
                            metrics["np_power"], metrics["tss"], metrics["intensity_factor"], metrics["variability_index"],
                            metrics["avg_power"], metrics["avg_hr"], metrics["avg_cadence"],
                            pb_map.get(60), pb_map.get(300), pb_map.get(1200), pb_map.get(3600),
                            ride_id,
                        ),
                    )
                    
                    # Power bests
                    if metrics["power_bests"]:
                        conn.executemany(
                            "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            [(ride_id, date, pb["duration_s"], pb["power"], pb.get("avg_hr"), pb.get("avg_cadence"), pb.get("start_offset_s")) for pb in metrics["power_bests"]]
                        )
                
                # Fetch and store laps
                intervals = await asyncio.to_thread(fetch_activity_intervals, icu_id)
                if intervals:
                    laps = map_intervals_to_laps(intervals)
                    if laps:
                        _store_laps(ride_id, laps, conn=conn)

                conn.commit()
                repaired += 1
                logger.info("  + Repaired successfully")

        except Exception as e:
            logger.error("  ! Error repairing ride %d: %s", ride_id, e)
            failed += 1

    # Final rebuild of PMC
    if repaired > 0:
        logger.info("Rebuilding PMC for all days...")
        with get_db() as conn:
            compute_daily_pmc(conn)
            conn.commit()

    logger.info("Repair complete: %d rides repaired, %d failed.", repaired, failed)

if __name__ == "__main__":
    asyncio.run(repair_missing_data())
