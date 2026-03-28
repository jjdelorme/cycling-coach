"""Data ingestion: reads ride JSON files and ZWO workouts into PostgreSQL."""

import bisect
import json
import logging
import os
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict

from server.database import init_db, get_db

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("COACH_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
RIDES_DIR = os.path.join(DATA_DIR, "rides")
WORKOUTS_DIR = os.path.join(DATA_DIR, "planned_workouts")

POWER_BEST_DURATIONS = [5, 30, 60, 300, 1200, 3600]  # seconds


def file_hash(filepath):
    return hashlib.md5(open(filepath, "rb").read()).hexdigest()


def compute_rolling_best(powers, window_s):
    if len(powers) < window_s:
        return None
    best = 0
    current_sum = sum(powers[:window_s])
    best = current_sum
    for i in range(window_s, len(powers)):
        current_sum += powers[i] - powers[i - window_s]
        if current_sum > best:
            best = current_sum
    return round(best / window_s)


def parse_ride_json(filepath):
    with open(filepath) as f:
        data = json.load(f)

    session = data.get("session", [{}])[0]
    sport_info = data.get("sport", [{}])[0]
    user = data.get("user_profile", [{}])[0]
    records = data.get("record", [])

    start_time = session.get("start_time", session.get("timestamp", ""))
    if not start_time or not session.get("total_timer_time"):
        return None, None, None

    ftp = session.get("threshold_power", 0) or 0
    avg_power = session.get("avg_power", 0) or 0
    np_power = session.get("normalized_power", 0) or 0

    vi = 0
    if avg_power > 0 and np_power > 0:
        vi = round(np_power / avg_power, 3)

    total_work = session.get("total_work", 0) or 0

    # Extract power samples for best-power calculations
    powers = [r.get("power", 0) or 0 for r in records]

    best_1min = compute_rolling_best(powers, 60) if powers else None
    best_5min = compute_rolling_best(powers, 300) if powers else None
    best_20min = compute_rolling_best(powers, 1200) if powers else None
    best_60min = compute_rolling_best(powers, 3600) if powers else None

    # GPS start position
    start_lat = session.get("start_position_lat")
    start_lon = session.get("start_position_long")
    # Garmin stores lat/lon as semicircles, convert if very large
    if start_lat and abs(start_lat) > 180:
        start_lat = start_lat * (180 / 2**31)
    if start_lon and abs(start_lon) > 180:
        start_lon = start_lon * (180 / 2**31)

    ride = {
        "date": start_time[:10] if len(start_time) >= 10 else start_time,
        "start_time": start_time,
        "filename": os.path.basename(filepath),
        "sport": sport_info.get("sport", "unknown"),
        "sub_sport": sport_info.get("sub_sport", "unknown"),
        "duration_s": session.get("total_timer_time", 0),
        "distance_m": session.get("total_distance", 0),
        "avg_power": avg_power,
        "normalized_power": np_power,
        "max_power": session.get("max_power", 0),
        "avg_hr": session.get("avg_heart_rate", 0),
        "max_hr": session.get("max_heart_rate", 0),
        "avg_cadence": session.get("avg_cadence", 0),
        "total_ascent": session.get("total_ascent", 0),
        "total_descent": session.get("total_descent", 0),
        "total_calories": session.get("total_calories", 0),
        "tss": session.get("training_stress_score", 0),
        "intensity_factor": session.get("intensity_factor", 0),
        "ftp": ftp,
        "total_work_kj": round(total_work / 1000, 1) if total_work else 0,
        "training_effect": session.get("total_training_effect", 0),
        "variability_index": vi,
        "best_1min_power": best_1min,
        "best_5min_power": best_5min,
        "best_20min_power": best_20min,
        "best_60min_power": best_60min,
        "weight": user.get("weight"),
        "start_lat": start_lat,
        "start_lon": start_lon,
    }

    # If no power-based TSS but we have HR data, compute hrTSS
    if (not ride["tss"] or ride["tss"] == 0) and ride["avg_hr"] and ride["avg_hr"] > 0:
        from server.database import get_athlete_setting
        try:
            lthr = float(get_athlete_setting("lthr"))
            max_hr_setting = float(get_athlete_setting("max_hr"))
            resting_hr = float(get_athlete_setting("resting_hr"))
            hr_tss = compute_hr_tss(ride["avg_hr"], ride["duration_s"], lthr, max_hr_setting, resting_hr)
            if hr_tss > 0:
                ride["tss"] = hr_tss
        except (ValueError, TypeError):
            pass  # athlete settings not configured yet

    # Build record rows
    record_rows = []
    for r in records:
        lat = r.get("position_lat")
        lon = r.get("position_long")
        if lat and abs(lat) > 180:
            lat = lat * (180 / 2**31)
        if lon and abs(lon) > 180:
            lon = lon * (180 / 2**31)
        record_rows.append({
            "timestamp": r.get("timestamp", ""),
            "power": r.get("power"),
            "heart_rate": r.get("heart_rate"),
            "cadence": r.get("cadence"),
            "speed": r.get("enhanced_speed"),
            "altitude": r.get("enhanced_altitude"),
            "distance": r.get("distance"),
            "lat": lat,
            "lon": lon,
            "temperature": r.get("temperature"),
        })

    # Power bests at standard durations
    power_bests = []
    for dur in POWER_BEST_DURATIONS:
        best = compute_rolling_best(powers, dur)
        if best and best > 0:
            power_bests.append({"duration_s": dur, "power": best})

    return ride, record_rows, power_bests


def parse_zwo(filepath):
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError:
        return None

    fname = os.path.basename(filepath)
    date_str = fname[:10] if len(fname) >= 10 else None

    name_el = root.find("name")
    sport_el = root.find("sportType")
    workout_el = root.find("workout")

    total_duration = 0
    if workout_el is not None:
        for child in workout_el:
            total_duration += float(child.get("Duration", 0))

    with open(filepath) as f:
        xml_content = f.read()

    return {
        "date": date_str,
        "name": name_el.text if name_el is not None else fname,
        "sport": sport_el.text if sport_el is not None else "bike",
        "total_duration_s": total_duration,
        "workout_xml": xml_content,
    }


def compute_hr_tss(avg_hr: float, duration_s: float, lthr: float, max_hr: float, resting_hr: float) -> float:
    """Compute heart-rate-based TSS (hrTSS) using the exponential TRIMP model.

    This is the standard formula used by TrainingPeaks when power data is unavailable.
    hrTSS approximates the training stress using heart rate relative to lactate threshold.

    Args:
        avg_hr: Average heart rate for the activity (bpm).
        duration_s: Duration of the activity (seconds).
        lthr: Lactate threshold heart rate (bpm).
        max_hr: Maximum heart rate (bpm).
        resting_hr: Resting heart rate (bpm).

    Returns:
        Estimated TSS value, or 0 if inputs are invalid.
    """
    import math

    hr_range = max_hr - resting_hr
    if hr_range <= 0 or lthr <= resting_hr or duration_s <= 0 or avg_hr <= resting_hr:
        return 0.0

    duration_h = duration_s / 3600.0

    # Heart rate reserve ratio for the activity
    hr_ratio = (avg_hr - resting_hr) / hr_range

    # Heart rate reserve ratio at LTHR (the reference point = 100 TSS/hr)
    lthr_ratio = (lthr - resting_hr) / hr_range

    # Exponential TRIMP factor
    trimp_activity = hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
    trimp_lthr = lthr_ratio * 0.64 * math.exp(1.92 * lthr_ratio)

    if trimp_lthr <= 0:
        return 0.0

    hr_tss = (duration_h * trimp_activity / trimp_lthr) * 100.0
    return round(hr_tss, 1)


def backfill_hr_tss(conn):
    """Backfill hrTSS for rides that have HR data but no power-based TSS."""
    from server.database import get_athlete_setting

    lthr = float(get_athlete_setting("lthr"))
    max_hr = float(get_athlete_setting("max_hr"))
    resting_hr = float(get_athlete_setting("resting_hr"))

    rows = conn.execute(
        "SELECT id, avg_hr, duration_s FROM rides WHERE (tss IS NULL OR tss = 0) AND avg_hr > 0 AND duration_s > 0"
    ).fetchall()

    updated = 0
    for r in rows:
        hr_tss = compute_hr_tss(
            avg_hr=float(r["avg_hr"]),
            duration_s=float(r["duration_s"]),
            lthr=lthr,
            max_hr=max_hr,
            resting_hr=resting_hr,
        )
        if hr_tss > 0:
            conn.execute("UPDATE rides SET tss = ? WHERE id = ?", (hr_tss, r["id"]))
            updated += 1

    logger.info("Backfilled hrTSS for %d rides (of %d without TSS)", updated, len(rows))
    return updated


def compute_daily_pmc(conn, since_date: str | None = None):
    """Compute CTL/ATL/TSB for every day from first ride (or since_date) to today.

    Args:
        conn: Database connection.
        since_date: Optional YYYY-MM-DD string. If provided, carry forward
            CTL/ATL from the previous day and only recompute from this date.
            Falls back to full recompute if no previous day data exists.
    """
    cursor = conn.execute(
        "SELECT date, SUM(tss) as total_tss FROM rides WHERE tss > 0 GROUP BY date ORDER BY date"
    )
    daily_tss = {row["date"]: row["total_tss"] for row in cursor.fetchall()}

    if not daily_tss:
        return

    # Prefetch all weight data (eliminates N+1 queries)
    weight_rows = conn.execute(
        "SELECT date, weight FROM rides WHERE weight IS NOT NULL ORDER BY date"
    ).fetchall()
    weight_dates = [r["date"] for r in weight_rows]
    weight_values = [r["weight"] for r in weight_rows]

    def _lookup_weight(ds: str):
        """O(log n) weight lookup using bisect."""
        if not weight_dates:
            return None
        idx = bisect.bisect_right(weight_dates, ds) - 1
        return weight_values[idx] if idx >= 0 else None

    all_ride_dates = list(daily_tss.keys())
    end = datetime.today()

    ctl = 0.0
    atl = 0.0

    # Determine start point
    if since_date:
        prev_day = (datetime.fromisoformat(since_date) - timedelta(days=1)).strftime("%Y-%m-%d")
        prev = conn.execute(
            "SELECT ctl, atl FROM daily_metrics WHERE date = ?", (prev_day,)
        ).fetchone()
        if prev:
            ctl = prev["ctl"]
            atl = prev["atl"]
            start = datetime.fromisoformat(since_date)
        else:
            # No previous data — fall back to full recompute
            start = datetime.fromisoformat(min(all_ride_dates))
    else:
        start = datetime.fromisoformat(min(all_ride_dates))

    day = start
    pmc_rows = []

    while day <= end:
        ds = day.strftime("%Y-%m-%d")
        tss = daily_tss.get(ds, 0)
        ctl = ctl + (tss - ctl) / 42
        atl = atl + (tss - atl) / 7
        tsb = ctl - atl
        weight = _lookup_weight(ds)

        pmc_rows.append((ds, round(tss, 1), round(ctl, 1), round(atl, 1), round(tsb, 1), weight))
        day += timedelta(days=1)

    # Batch upsert all rows
    conn.executemany(
        "INSERT INTO daily_metrics (date, total_tss, ctl, atl, tsb, weight) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (date) DO UPDATE SET "
        "total_tss = EXCLUDED.total_tss, ctl = EXCLUDED.ctl, "
        "atl = EXCLUDED.atl, tsb = EXCLUDED.tsb, weight = EXCLUDED.weight",
        pmc_rows,
    )


def seed_periodization(conn):
    """Insert the default periodization phases if not already present."""
    existing = conn.execute("SELECT COUNT(*) as cnt FROM periodization_phases").fetchone()["cnt"]
    if existing > 0:
        return

    phases = [
        ("Base Rebuild", "2026-03-23", "2026-04-27", "Aerobic base, rebuild CTL from 21 to 50", 10, 12, 350, 500),
        ("Build 1", "2026-04-28", "2026-06-01", "Add threshold work, CTL 50 to 70", 12, 14, 500, 650),
        ("Build 2", "2026-06-02", "2026-07-06", "Add VO2max, race-pace rides, CTL 70 to 85", 13, 15, 600, 750),
        ("Peak", "2026-07-07", "2026-08-10", "Race-simulation rides, long MTB, CTL 85-90", 12, 14, 550, 700),
        ("Taper", "2026-08-11", "2026-08-29", "Volume down 40%, keep intensity, CTL ~82", 7, 9, 300, 400),
    ]
    for p in phases:
        conn.execute(
            "INSERT INTO periodization_phases (name, start_date, end_date, focus, hours_per_week_low, hours_per_week_high, tss_target_low, tss_target_high) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            p,
        )


def ingest_rides(conn, rides_dir=None):
    rides_dir = rides_dir or RIDES_DIR
    if not os.path.isdir(rides_dir):
        logger.warning("Rides directory not found: %s", rides_dir)
        return 0

    # Get already-ingested filenames
    existing = set(
        row["filename"]
        for row in conn.execute("SELECT filename FROM rides").fetchall()
    )

    json_files = sorted(f for f in os.listdir(rides_dir) if f.endswith(".json"))
    ingested = 0

    for fname in json_files:
        if fname in existing:
            continue

        filepath = os.path.join(rides_dir, fname)
        ride, records, power_bests = parse_ride_json(filepath)

        if ride is None:
            continue

        cursor = conn.execute(
            """INSERT INTO rides (date, start_time, filename, sport, sub_sport, duration_s, distance_m,
               avg_power, normalized_power, max_power, avg_hr, max_hr, avg_cadence,
               total_ascent, total_descent, total_calories, tss, intensity_factor,
               ftp, total_work_kj, training_effect, variability_index,
               best_1min_power, best_5min_power, best_20min_power, best_60min_power,
               weight, start_lat, start_lon)
            VALUES (:date, :start_time, :filename, :sport, :sub_sport, :duration_s, :distance_m,
               :avg_power, :normalized_power, :max_power, :avg_hr, :max_hr, :avg_cadence,
               :total_ascent, :total_descent, :total_calories, :tss, :intensity_factor,
               :ftp, :total_work_kj, :training_effect, :variability_index,
               :best_1min_power, :best_5min_power, :best_20min_power, :best_60min_power,
               :weight, :start_lat, :start_lon) RETURNING id""",
            ride,
        )
        row = cursor.fetchone()
        ride_id = row["id"] if isinstance(row, dict) else row[0]

        # Insert records in batches
        if records:
            for i in range(0, len(records), 1000):
                batch = records[i : i + 1000]
                conn.executemany(
                    """INSERT INTO ride_records (ride_id, timestamp_utc, power, heart_rate, cadence,
                       speed, altitude, distance, lat, lon, temperature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (ride_id, r["timestamp"], r["power"], r["heart_rate"], r["cadence"],
                         r["speed"], r["altitude"], r["distance"], r["lat"], r["lon"], r["temperature"])
                        for r in batch
                    ],
                )

        # Insert power bests
        if power_bests:
            conn.executemany(
                "INSERT INTO power_bests (ride_id, date, duration_s, power) VALUES (?, ?, ?, ?)",
                [(ride_id, ride["date"], pb["duration_s"], pb["power"]) for pb in power_bests],
            )

        ingested += 1

    return ingested


def ingest_workouts(conn, workouts_dir=None):
    workouts_dir = workouts_dir or WORKOUTS_DIR
    if not os.path.isdir(workouts_dir):
        logger.warning("Workouts directory not found: %s", workouts_dir)
        return 0

    # Check if we already have workouts
    existing_count = conn.execute("SELECT COUNT(*) as cnt FROM planned_workouts").fetchone()["cnt"]
    if existing_count > 0:
        return 0

    zwo_files = sorted(f for f in os.listdir(workouts_dir) if f.endswith(".zwo"))
    ingested = 0

    for fname in zwo_files:
        filepath = os.path.join(workouts_dir, fname)
        workout = parse_zwo(filepath)
        if workout is None:
            continue

        from server.services.workout_generator import calculate_planned_tss
        workout["planned_tss"] = calculate_planned_tss(workout.get("workout_xml"))
        conn.execute(
            "INSERT INTO planned_workouts (date, name, sport, total_duration_s, planned_tss, workout_xml) VALUES (:date, :name, :sport, :total_duration_s, :planned_tss, :workout_xml)",
            workout,
        )
        ingested += 1

    return ingested


def run_ingestion():
    """Full ingestion pipeline."""
    init_db()
    logger.info("Database: %s", os.environ.get("DATABASE_URL", "localhost"))

    with get_db() as conn:
        logger.info("Ingesting rides...")
        ride_count = ingest_rides(conn)
        logger.info("Ingested %d new rides", ride_count)

        logger.info("Ingesting planned workouts...")
        workout_count = ingest_workouts(conn)
        logger.info("Ingested %d planned workouts", workout_count)

        logger.info("Backfilling hrTSS for rides without power...")
        backfill_hr_tss(conn)

        logger.info("Computing PMC (CTL/ATL/TSB)...")
        compute_daily_pmc(conn)

        logger.info("Seeding periodization phases...")
        seed_periodization(conn)

        # Summary
        total_rides = conn.execute("SELECT COUNT(*) as cnt FROM rides").fetchone()["cnt"]
        total_records = conn.execute("SELECT COUNT(*) as cnt FROM ride_records").fetchone()["cnt"]
        total_workouts = conn.execute("SELECT COUNT(*) as cnt FROM planned_workouts").fetchone()["cnt"]
        total_pmc = conn.execute("SELECT COUNT(*) as cnt FROM daily_metrics").fetchone()["cnt"]

        logger.info("Database summary: Rides=%d Records=%d Workouts=%d PMC=%d",
                     total_rides, total_records, total_workouts, total_pmc)


if __name__ == "__main__":
    run_ingestion()
