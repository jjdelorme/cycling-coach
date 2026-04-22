import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import get_db
from server.logging_config import get_logger
from server.services.intervals_icu import _get_credentials, fetch_activity_fit_laps, fetch_activity_streams, is_configured, map_activity_to_ride
from server.services.sync import _enrich_laps_with_np, _extract_streams, _store_laps, _store_streams, _backfill_start_location, _backfill_start_from_laps
from server.metrics import process_ride_samples
from server.queries import get_latest_metric
from server.ingest import get_benchmark_for_date

import httpx

logger = get_logger(__name__)

async def import_specific_activity(icu_id):
    if not is_configured():
        logger.error("single_sync_not_configured", icu_id=icu_id)
        raise ValueError("Intervals.icu is not configured.")

    api_key, athlete_id = _get_credentials()

    url = f"https://intervals.icu/api/v1/activity/{icu_id}"
    logger.info("single_sync_fetch_start", icu_id=icu_id)
    resp = httpx.get(url, auth=("API_KEY", api_key), timeout=10.0)
    if resp.status_code != 200:
        logger.error("single_sync_fetch_failed", icu_id=icu_id, status=resp.status_code)
        raise ValueError(f"Failed to fetch activity {icu_id}: {resp.status_code}")

    activity = resp.json()
    ride_data = map_activity_to_ride(activity)

    if not ride_data:
        logger.error("single_sync_map_failed", icu_id=icu_id)
        raise ValueError(f"Activity {icu_id} could not be mapped to a ride.")
    # Derive UTC date from start_time for benchmark lookups and power_bests.date
    target_date = ride_data["start_time"][:10] if ride_data.get("start_time") else ""
    logger.info("single_sync_mapped", icu_id=icu_id, date=target_date, sport=ride_data["sport"])
    
    filename = f"icu_{icu_id}"
    
    with get_db() as conn:
        ride = conn.execute("SELECT id FROM rides WHERE filename = %(f)s", {"f": filename}).fetchone()
        if ride:
            ride_id = ride["id"]
            logger.info("single_sync_updating", icu_id=icu_id, ride_id=ride_id)

            # Clear old records and reset GPS so _backfill_start_location can re-run
            conn.execute("DELETE FROM ride_records WHERE ride_id = %(id)s", {"id": ride_id})
            conn.execute("DELETE FROM power_bests WHERE ride_id = %(id)s", {"id": ride_id})
            conn.execute(
                "UPDATE rides SET start_lat = NULL, start_lon = NULL WHERE id = %(id)s",
                {"id": ride_id},
            )
        else:
            logger.info("single_sync_inserting", icu_id=icu_id, date=target_date)
            res = conn.execute(
                """INSERT INTO rides
                   (start_time, title, duration_s, distance_m, total_ascent,
                    sport, avg_power, max_power, avg_hr, max_hr, avg_cadence,
                    normalized_power, tss, intensity_factor, variability_index, filename, ftp,
                    best_1min_power, best_5min_power, best_20min_power, best_60min_power)
                   VALUES
                   (%(st)s, %(title)s, %(dur)s, %(dist)s, %(elev)s,
                    %(sport)s, %(ap)s, %(mp)s, %(ahr)s, %(mhr)s, %(acad)s,
                    %(np)s, %(tss)s, %(if)s, %(vi)s, %(file)s, %(ftp)s,
                    %(b1)s, %(b5)s, %(b20)s, %(b60)s)
                   RETURNING id""",
                {
                    "st": ride_data.get("start_time"), "title": activity.get("name", "Activity"),
                    "dur": ride_data["duration_s"], 
                    "dist": ride_data.get("distance_m", 0),
                    "elev": ride_data.get("total_ascent"), "sport": ride_data.get("sport", "Ride"), 
                    "ap": ride_data.get("avg_power"), "mp": ride_data.get("max_power"),
                    "ahr": ride_data.get("avg_hr"), "mhr": ride_data.get("max_hr"),
                    "acad": ride_data.get("avg_cadence"),
                    "np": ride_data.get("normalized_power"), "tss": ride_data.get("tss"), "if": ride_data.get("intensity_factor"),
                    "vi": ride_data.get("variability_index"),
                    "file": filename, "ftp": ride_data.get("ftp"),
                    "b1": ride_data.get("best_1min_power"), "b5": ride_data.get("best_5min_power"), 
                    "b20": ride_data.get("best_20min_power"), "b60": ride_data.get("best_60min_power")
                }
            ).fetchone()
            ride_id = res["id"]
            
        logger.info("single_sync_fetch_streams", icu_id=icu_id)
        streams = fetch_activity_streams(icu_id)
        sport = ride_data.get("sport", "").lower()
        is_cycling = sport in ('ride', 'ebikeride', 'emountainbikeride', 'gravelride', 'mountainbikeride', 'trackride', 'velomobile', 'virtualride', 'handcycle', 'cycling')
        stream_map = {}
        if streams:
            logger.info("single_sync_storing_streams", icu_id=icu_id, ride_id=ride_id)
            _store_streams(ride_id, streams, conn=conn)
            _backfill_start_location(ride_id, streams, conn=conn)

            stream_map = _extract_streams(streams)
            raw_powers = stream_map.get("watts", []) if is_cycling else []
            raw_hrs = stream_map.get("heartrate", [])
            raw_cadences = stream_map.get("cadence", [])
            
            lthr = get_latest_metric(conn, "lthr", target_date)
            max_hr_setting = get_latest_metric(conn, "max_hr", target_date)
            resting_hr = get_latest_metric(conn, "resting_hr", target_date)
            
            ftp = get_benchmark_for_date(conn, "ftp", target_date)
            if ftp <= 0:
                ftp = ride_data.get("ftp") or 0
                
            logger.info("single_sync_processing_metrics", icu_id=icu_id, ftp=ftp)
            metrics = process_ride_samples(
                raw_powers, raw_hrs, raw_cadences, ftp, ride_data["duration_s"],
                lthr=lthr, max_hr=max_hr_setting, resting_hr=resting_hr
            )
            
            if metrics["has_power_data"]:
                pb_map = {pb["duration_s"]: pb["power"] for pb in metrics["power_bests"]}
                conn.execute(
                    """UPDATE rides SET 
                       normalized_power = %(np)s, tss = %(tss)s, intensity_factor = %(if_val)s, variability_index = %(vi)s,
                       avg_power = %(ap)s, avg_hr = %(ahr)s, avg_cadence = %(acad)s,
                       best_1min_power = %(b1)s, best_5min_power = %(b5)s, best_20min_power = %(b20)s, best_60min_power = %(b60)s,
                       has_power_data = TRUE, data_status = %(status)s
                       WHERE id = %(id)s""",
                    {
                        "np": metrics["np_power"], "tss": metrics["tss"], "if_val": metrics["intensity_factor"],
                        "vi": metrics["variability_index"], "ap": metrics["avg_power"], "ahr": metrics["avg_hr"],
                        "acad": metrics["avg_cadence"], "b1": pb_map.get(60), "b5": pb_map.get(300),
                        "b20": pb_map.get(1200), "b60": pb_map.get(3600), "status": metrics["data_status"], "id": ride_id
                    }
                )
            else:
                conn.execute(
                    """UPDATE rides SET 
                       avg_hr = %(ahr)s, avg_cadence = %(acad)s,
                       normalized_power = NULL, avg_power = NULL, max_power = NULL,
                       intensity_factor = NULL, variability_index = NULL,
                       best_1min_power = NULL, best_5min_power = NULL, best_20min_power = NULL, best_60min_power = NULL,
                       has_power_data = FALSE, data_status = %(status)s
                       WHERE id = %(id)s""", 
                    {"ahr": metrics.get("avg_hr"), "acad": metrics.get("avg_cadence"), "status": metrics.get("data_status", "raw"), "id": ride_id}
                )
                if metrics.get("tss", 0) > 0:
                    conn.execute("UPDATE rides SET tss = %(tss)s WHERE id = %(id)s", {"tss": metrics["tss"], "id": ride_id})
            
            # Insert power bests (date is UTC-derived from start_time)
            if metrics.get("power_bests"):
                params_list = [
                    {"ride_id": ride_id, "date": target_date, "dur": pb["duration_s"], "pwr": pb["power"],
                     "ahr": pb.get("avg_hr"), "acad": pb.get("avg_cadence"), "offset": pb.get("start_offset_s")}
                    for pb in metrics["power_bests"]
                ]
                conn.executemany(
                    "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (%(ride_id)s, %(date)s, %(dur)s, %(pwr)s, %(ahr)s, %(acad)s, %(offset)s)",
                    params_list
                )
            logger.info("single_sync_complete", icu_id=icu_id, sport=ride_data.get("sport"), tss=metrics.get("tss"), has_power=metrics.get("has_power_data"))
        else:
            logger.warning("single_sync_no_streams", icu_id=icu_id)
            logger.info("single_sync_complete", icu_id=icu_id, sport=ride_data.get("sport"), tss=ride_data.get("tss"), has_power=False)

        # Fetch and store device laps from FIT file
        try:
            conn.execute("DELETE FROM ride_laps WHERE ride_id = %(id)s", {"id": ride_id})
            laps = fetch_activity_fit_laps(icu_id)
            if laps:
                # Calculate NP per lap from stream power data
                if streams and is_cycling and stream_map:
                    _enrich_laps_with_np(laps, stream_map)
                _store_laps(ride_id, laps, conn=conn)
                _backfill_start_from_laps(ride_id, laps, conn=conn)
                logger.info("single_sync_laps_stored", icu_id=icu_id, lap_count=len(laps))
        except Exception as e:
            logger.warning("single_sync_laps_failed", icu_id=icu_id, error=str(e))

        conn.commit()

if __name__ == "__main__":
    asyncio.run(import_specific_activity("i134594126"))
