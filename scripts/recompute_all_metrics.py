import sys
import os
import logging
import numpy as np

# Add the project root to sys.path to import server modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.database import get_db
from server.metrics import clean_ride_data, calculate_np, calculate_tss
from server.queries import get_latest_metric
from server.ingest import compute_rolling_best, compute_daily_pmc, POWER_BEST_DURATIONS, compute_hr_tss

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def recompute_all_metrics():
    with get_db() as conn:
        logger.info("Fetching all rides...")
        # Select necessary columns to update and recalculate
        rides = conn.execute("SELECT id, date, duration_s, avg_hr, avg_cadence, filename, sport FROM rides ORDER BY date").fetchall()
        logger.info(f"Found {len(rides)} rides to process.")

        for i, ride in enumerate(rides):
            ride_id = ride['id']
            ride_date = ride['date']
            duration_s = ride['duration_s']
            filename = ride['filename']
            
            logger.info(f"[{i+1}/{len(rides)}] Processing ride {ride_id} ({ride_date}, {filename})...")
            
            # Fetch latest point-in-time metrics
            ftp = get_latest_metric(conn, 'ftp', ride_date)
            weight = get_latest_metric(conn, 'weight_kg', ride_date)

            # 1. Fetch records
            records = conn.execute(
                "SELECT power, heart_rate, cadence FROM ride_records WHERE ride_id = %s ORDER BY timestamp_utc",
                (ride_id,)
            ).fetchall()
            
            if not records:
                logger.warning(f"No records found for ride {ride_id}. Updating FTP and Weight only.")
                conn.execute(
                    "UPDATE rides SET ftp = %s, weight = %s WHERE id = %s",
                    (ftp, weight, ride_id)
                )
                continue

            sport = (ride.get('sport') or '').lower()
            is_cycling = sport in ('ride', 'ebikeride', 'emountainbikeride', 'gravelride', 'mountainbikeride', 'trackride', 'velomobile', 'virtualride', 'handcycle', 'cycling')
            
            raw_powers = [r['power'] for r in records] if is_cycling else []
            raw_hrs = [r['heart_rate'] for r in records]
            raw_cadences = [r['cadence'] for r in records]
            
            # 2. Clean data
            cleaned_p, cleaned_hr, cleaned_cadence = clean_ride_data(raw_powers, raw_hrs, raw_cadences)
            
            has_power_data = any(p is not None and not np.isnan(p) and p > 0 for p in (cleaned_p if cleaned_p is not None else []))
            data_status = 'cleaned' if has_power_data else 'raw'
            
            # Convert back to native types for storage/rolling bests
            powers_vec = np.nan_to_num(cleaned_p, nan=0.0) if cleaned_p is not None else np.array([])
            hrs = [int(h) if not np.isnan(h) else None for h in cleaned_hr] if cleaned_hr is not None else []
            cadences = [int(c) if not np.isnan(c) else None for c in cleaned_cadence] if cleaned_cadence is not None else []

            # 3. Recalculate metrics
            np_power = 0
            tss = 0
            if_val = 0
            avg_p = 0
            
            # Recalculate avg_hr and avg_cadence from cleaned data
            avg_hr = ride['avg_hr']
            if hrs:
                valid_hrs = [h for h in hrs if h is not None]
                avg_hr = round(sum(valid_hrs) / len(valid_hrs)) if valid_hrs else avg_hr
            
            avg_cadence = ride['avg_cadence']
            if cadences:
                valid_cadences = [c for c in cadences if c is not None]
                avg_cadence = round(sum(valid_cadences) / len(valid_cadences)) if valid_cadences else avg_cadence

            # 5. Recalculate power bests
            best_1min = None
            best_5min = None
            best_20min = None
            best_60min = None
            
            if has_power_data:
                np_power = calculate_np(powers_vec)
                tss = calculate_tss(np_power, duration_s, ftp)
                avg_p = round(np.mean(powers_vec))
                if_val = round(np_power / ftp, 3) if ftp > 0 else 0
                
                # Delete old power bests
                conn.execute("DELETE FROM power_bests WHERE ride_id = %s", (ride_id,))
                
                new_power_bests = []
                for dur in POWER_BEST_DURATIONS:
                    res = compute_rolling_best(powers_vec, dur, hrs=hrs, cadences=cadences)
                    if res and res["power"] > 0:
                        new_power_bests.append((
                            ride_id, ride_date, dur, res["power"], 
                            res.get("avg_hr"), res.get("avg_cadence"), res.get("start_offset_s")
                        ))
                
                if new_power_bests:
                    conn.executemany(
                        "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        new_power_bests
                    )
                    
                    # Extract standard bests for rides table
                    best_1min = next((pb[3] for pb in new_power_bests if pb[2] == 60), None)
                    best_5min = next((pb[3] for pb in new_power_bests if pb[2] == 300), None)
                    best_20min = next((pb[3] for pb in new_power_bests if pb[2] == 1200), None)
                    best_60min = next((pb[3] for pb in new_power_bests if pb[2] == 3600), None)
            else:
                # If no power, try hrTSS
                if avg_hr and avg_hr > 0:
                    lthr = get_latest_metric(conn, "lthr", ride_date)
                    max_hr_setting = get_latest_metric(conn, "max_hr", ride_date)
                    resting_hr = get_latest_metric(conn, "resting_hr", ride_date)
                    if lthr > 0:
                        tss = compute_hr_tss(avg_hr, duration_s, lthr, max_hr_setting, resting_hr)

            # 4. Update rides table
            if has_power_data:
                conn.execute(
                    """UPDATE rides SET 
                       normalized_power = %s, tss = %s, intensity_factor = %s, avg_power = %s, 
                       has_power_data = %s, data_status = %s, ftp = %s, weight = %s,
                       avg_hr = %s, avg_cadence = %s,
                       best_1min_power = %s, best_5min_power = %s, best_20min_power = %s, best_60min_power = %s
                       WHERE id = %s""",
                    (np_power, tss, if_val, avg_p, True, data_status, ftp, weight, avg_hr, avg_cadence, 
                     best_1min, best_5min, best_20min, best_60min, ride_id)
                )
            else:
                conn.execute(
                    """UPDATE rides SET 
                       tss = %s, 
                       normalized_power = NULL, intensity_factor = NULL, avg_power = NULL, max_power = NULL,
                       has_power_data = FALSE, data_status = %s, ftp = %s, weight = %s,
                       avg_hr = %s, avg_cadence = %s,
                       best_1min_power = NULL, best_5min_power = NULL, best_20min_power = NULL, best_60min_power = NULL
                       WHERE id = %s""",
                    (tss, data_status, ftp, weight, avg_hr, avg_cadence, ride_id)
                )
            
            # Commit every 10 rides to avoid huge transactions
            if (i + 1) % 10 == 0:
                conn.commit()
                logger.info(f"Committed {i+1} rides.")

        # Final commit for remaining rides
        conn.commit()
        
        # 6. Rebuild daily_metrics
        logger.info("Rebuilding daily_metrics table...")
        # Optional: truncate daily_metrics to ensure a completely fresh start
        conn.execute("DELETE FROM daily_metrics")
        conn.commit()
        compute_daily_pmc(conn)
        logger.info("Daily metrics rebuilt successfully.")

if __name__ == "__main__":
    recompute_all_metrics()
