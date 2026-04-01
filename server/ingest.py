"""Data ingestion: reads ride JSON files and ZWO workouts into PostgreSQL."""

import bisect
import json
import logging
import os
import numpy as np
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict

from server.database import init_db, get_db
from server.metrics import (
    clean_ride_data, 
    calculate_np, 
    calculate_tss, 
    POWER_BEST_DURATIONS, 
    compute_rolling_best, 
    compute_hr_tss, 
    process_ride_samples
)

logger = logging.getLogger(__name__)


def _semicircles_to_degrees(val):
    """Convert Garmin semicircle coordinates to decimal degrees, or return None."""
    if val is None:
        return None
    if abs(val) > 180:
        return val * (180 / 2**31)
    return val


def file_hash(filepath):
    return hashlib.md5(open(filepath, "rb").read()).hexdigest()


def get_benchmark_for_date(conn, key: str, date_str: str) -> float:
    """Get the active benchmark for a specific date using the hierarchy.
    
    Hierarchy:
    1. Historical athlete_settings entry <= as_of_date (Manual Override - Athlete's Word).
    2. Most recent ride on or before this date with this metric (File-as-Fallback).
    3. Final fallback to defaults.
    """
    # 1. Check historical athlete_settings (Manual Override)
    from server.queries import get_latest_metric
    val = get_latest_metric(conn, key, date_str)
    if val > 0:
        # Check if this came from an actual setting and not just the default
        from server.database import ATHLETE_SETTINGS_DEFAULTS
        if str(val) != str(ATHLETE_SETTINGS_DEFAULTS.get(key)):
            return val

    # 2. Look back to the most recent ride with this metric
    col = "ftp" if key == "ftp" else "weight"
    row = conn.execute(
        f"SELECT {col} FROM rides WHERE {col} > 0 AND date <= %s ORDER BY date DESC LIMIT 1",
        (date_str,)
    ).fetchone()
    if row and row[col]:
        return float(row[col])
    
    # 3. Final fallback (Defaults)
    return val


def parse_ride_json(filepath, conn=None):
    with open(filepath) as f:
        data = json.load(f)

    session = data.get("session", [{}])[0]
    sport_info = data.get("sport", [{}])[0]
    user = data.get("user_profile", [{}])[0]
    zones = data.get("zones_target", [{}])[0]
    records = data.get("record", [])

    start_time = session.get("start_time", session.get("timestamp", ""))
    if not start_time or not session.get("total_timer_time"):
        return None, None, None, None

    ride_date = start_time[:10] if len(start_time) >= 10 else start_time
    sport = (session.get("sport") or sport_info.get("sport") or "cycling").lower()

    # 1. Extract & Hierarchy for FTP/Weight
    # We START with the hierarchy (Settings > Previous Rides)
    ftp = 0
    weight = 0
    
    if conn:
        ftp = get_benchmark_for_date(conn, "ftp", ride_date)
        weight = get_benchmark_for_date(conn, "weight_kg", ride_date)
    
    # 2. Fallback to Source File ONLY if hierarchy returned 0/default
    # AND only extract FTP if this is a cycling activity
    is_cycling = sport in ("cycling", "virtualride", "mountainbikeride")
    
    if ftp <= 0 and is_cycling:
        ftp = (session.get("threshold_power", 0) or 
               session.get("functional_threshold_power", 0) or 
               zones.get("functional_threshold_power", 0)) or 0
               
    if weight <= 0:
        weight = user.get("weight") or 0
        
    # Final check: if still 0, use defaults
    if not conn:
        from server.database import get_athlete_setting
        if ftp <= 0: ftp = float(get_athlete_setting("ftp"))
        if weight <= 0: weight = float(get_athlete_setting("weight_kg"))

    # Extract raw samples for cleaning
    raw_powers = [r.get("power") for r in records]
    raw_hrs = [r.get("heart_rate") for r in records]
    raw_cadences = [r.get("cadence") for r in records]

    # 3. Process samples for metrics and power bests using the unified pipeline
    duration_s = session.get("total_timer_time", 0)
    
    # Fetch HR benchmarks for hrTSS fallback
    from server.queries import get_latest_metric
    lthr = 0
    max_hr_setting = 0
    resting_hr = 0
    try:
        if conn:
            lthr = get_latest_metric(conn, "lthr", ride_date)
            max_hr_setting = get_latest_metric(conn, "max_hr", ride_date)
            resting_hr = get_latest_metric(conn, "resting_hr", ride_date)
        else:
            from server.database import get_athlete_setting
            lthr = float(get_athlete_setting("lthr"))
            max_hr_setting = float(get_athlete_setting("max_hr"))
            resting_hr = float(get_athlete_setting("resting_hr"))
    except (ValueError, TypeError):
        pass

    metrics = process_ride_samples(
        raw_powers, raw_hrs, raw_cadences, 
        ftp, duration_s,
        lthr=lthr, max_hr=max_hr_setting, resting_hr=resting_hr
    )
    
    # Use recalculated metrics if we have power, otherwise fallback to session
    if metrics["has_power_data"]:
        avg_power = metrics["avg_power"]
        np_power = metrics["np_power"]
        tss = metrics["tss"]
        intensity_factor = metrics["intensity_factor"]
    else:
        avg_power = session.get("avg_power", 0) or 0
        np_power = session.get("normalized_power", 0) or 0
        # If no power data, prioritize the hrTSS from metrics if it's > 0, otherwise fallback to session
        tss = metrics["tss"] if metrics["tss"] > 0 else (session.get("training_stress_score", 0) or 0)
        intensity_factor = session.get("intensity_factor", 0) or 0

    vi = metrics["variability_index"]
    has_power_data = metrics["has_power_data"]
    data_status = metrics["data_status"]
    powers = metrics["powers"]
    hrs = metrics["hrs"]
    cadences = metrics["cadences"]
    power_bests = metrics["power_bests"]
    avg_hr = metrics["avg_hr"] or session.get("avg_heart_rate", 0) or 0
    avg_cadence = metrics["avg_cadence"] or session.get("avg_cadence", 0) or 0

    best_powers = {pb["duration_s"]: pb["power"] for pb in power_bests}

    # GPS start position
    start_lat = _semicircles_to_degrees(session.get("start_position_lat"))
    start_lon = _semicircles_to_degrees(session.get("start_position_long"))

    total_work = session.get("total_work", 0) or 0

    ride = {
        "date": start_time[:10] if len(start_time) >= 10 else start_time,
        "start_time": start_time,
        "filename": os.path.basename(filepath),
        "sport": sport_info.get("sport", "unknown"),
        "sub_sport": sport_info.get("sub_sport", "unknown"),
        "duration_s": duration_s,
        "distance_m": session.get("total_distance", 0),
        "avg_power": avg_power,
        "normalized_power": np_power,
        "max_power": session.get("max_power", 0),
        "avg_hr": avg_hr,
        "max_hr": session.get("max_heart_rate", 0),
        "avg_cadence": avg_cadence,
        "total_ascent": session.get("total_ascent", 0),
        "total_descent": session.get("total_descent", 0),
        "total_calories": session.get("total_calories", 0),
        "tss": tss,
        "intensity_factor": intensity_factor,
        "ftp": ftp,
        "total_work_kj": round(total_work / 1000, 1) if total_work else 0,
        "training_effect": session.get("total_training_effect", 0),
        "variability_index": vi,
        "best_1min_power": best_powers.get(60),
        "best_5min_power": best_powers.get(300),
        "best_20min_power": best_powers.get(1200),
        "best_60min_power": best_powers.get(3600),
        "weight": weight,
        "start_lat": start_lat,
        "start_lon": start_lon,
        "has_power_data": has_power_data,
        "data_status": data_status,
    }

    # Build record rows
    record_rows = []
    for i, r in enumerate(records):
        lat = _semicircles_to_degrees(r.get("position_lat"))
        lon = _semicircles_to_degrees(r.get("position_long"))
        record_rows.append({
            "timestamp": r.get("timestamp", ""),
            "power": powers[i] if i < len(powers) else None,
            "heart_rate": hrs[i] if i < len(hrs) else None,
            "cadence": cadences[i] if i < len(cadences) else None,
            "speed": r.get("enhanced_speed"),
            "altitude": r.get("enhanced_altitude"),
            "distance": r.get("distance"),
            "lat": lat,
            "lon": lon,
            "temperature": r.get("temperature"),
        })

    # Extract lap data
    laps = data.get("lap", [])
    lap_rows = []
    for lap in laps:
        intensity = lap.get("intensity")
        if not isinstance(intensity, str):
            intensity = None
        lap_trigger = lap.get("lap_trigger")
        if not isinstance(lap_trigger, str):
            lap_trigger = None
        lap_rows.append({
            "lap_index": lap.get("message_index", len(lap_rows)),
            "start_time": lap.get("start_time", ""),
            "total_timer_time": lap.get("total_timer_time"),
            "total_elapsed_time": lap.get("total_elapsed_time"),
            "total_distance": lap.get("total_distance"),
            "avg_power": lap.get("avg_power"),
            "normalized_power": lap.get("normalized_power"),
            "max_power": lap.get("max_power"),
            "avg_hr": lap.get("avg_heart_rate"),
            "max_hr": lap.get("max_heart_rate"),
            "avg_cadence": lap.get("avg_cadence"),
            "max_cadence": lap.get("max_cadence"),
            "avg_speed": lap.get("enhanced_avg_speed"),
            "max_speed": lap.get("enhanced_max_speed"),
            "total_ascent": lap.get("total_ascent"),
            "total_descent": lap.get("total_descent"),
            "total_calories": lap.get("total_calories"),
            "total_work": lap.get("total_work"),
            "intensity": intensity,
            "lap_trigger": lap_trigger,
            "wkt_step_index": lap.get("wkt_step_index"),
            "start_lat": _semicircles_to_degrees(lap.get("start_position_lat")),
            "start_lon": _semicircles_to_degrees(lap.get("start_position_long")),
            "end_lat": _semicircles_to_degrees(lap.get("end_position_lat")),
            "end_lon": _semicircles_to_degrees(lap.get("end_position_long")),
            "avg_temperature": lap.get("avg_temperature"),
        })

    # Calculate NP per lap from per-second power data
    if has_power_data and powers and lap_rows:
        import numpy as np_lib
        power_arr = np_lib.array(powers, dtype=float)
        offset = 0
        for lap_row in lap_rows:
            duration = lap_row.get("total_timer_time")
            if not duration or duration <= 0:
                offset += int(duration or 0)
                continue
            if lap_row.get("normalized_power"):
                offset += int(duration)
                continue
            end = offset + int(duration)
            lap_power = power_arr[offset:end]
            if len(lap_power) > 0:
                np_val = calculate_np(lap_power)
                if np_val and np_val > 0:
                    lap_row["normalized_power"] = int(round(np_val))
            offset = end

    return ride, record_rows, power_bests, lap_rows


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


def backfill_hr_tss(conn):
    """Backfill hrTSS for rides that have HR data but no power-based TSS."""
    from server.queries import get_latest_metric

    rows = conn.execute(
        "SELECT id, date, avg_hr, duration_s FROM rides WHERE (tss IS NULL OR tss = 0) AND avg_hr > 0 AND duration_s > 0"
    ).fetchall()

    updated = 0
    for r in rows:
        lthr = get_latest_metric(conn, "lthr", r["date"])
        max_hr = get_latest_metric(conn, "max_hr", r["date"])
        resting_hr = get_latest_metric(conn, "resting_hr", r["date"])

        if lthr <= 0:
            continue

        hr_tss = compute_hr_tss(
            avg_hr=float(r["avg_hr"]),
            duration_s=float(r["duration_s"]),
            lthr=lthr,
            max_hr=max_hr,
            resting_hr=resting_hr,
        )
        if hr_tss > 0:
            conn.execute("UPDATE rides SET tss = %s WHERE id = %s", (hr_tss, r["id"]))
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

    # Prefetch all weight and ftp data (eliminates N+1 queries)
    ride_data_rows = conn.execute(
        "SELECT date, weight, ftp FROM rides ORDER BY date"
    ).fetchall()
    ride_dates = [r["date"] for r in ride_data_rows]
    weight_values = [r["weight"] for r in ride_data_rows]
    ftp_values = [r["ftp"] for r in ride_data_rows]

    def _lookup_ride_metric(ds: str, values_list):
        """O(log n) metric lookup using bisect."""
        if not ride_dates:
            return None
        idx = bisect.bisect_right(ride_dates, ds) - 1
        return values_list[idx] if idx >= 0 else None

    # Prefetch athlete_settings for FTP/Weight as well
    settings_rows = conn.execute(
        "SELECT date_set, key, value FROM athlete_settings WHERE key IN ('ftp', 'weight_kg') ORDER BY date_set"
    ).fetchall()
    
    ftp_settings = [(r["date_set"], float(r["value"])) for r in settings_rows if r["key"] == "ftp"]
    weight_settings = [(r["date_set"], float(r["value"])) for r in settings_rows if r["key"] == "weight_kg"]

    def _lookup_setting_metric(ds: str, settings_list):
        if not settings_list:
            return None
        # bisect on the date_set
        dates = [s[0] for s in settings_list]
        idx = bisect.bisect_right(dates, ds) - 1
        return settings_list[idx][1] if idx >= 0 else None

    all_ride_dates = list(daily_tss.keys())
    end = datetime.today()

    ctl = 0.0
    atl = 0.0

    # Determine start point
    if since_date:
        prev_day = (datetime.fromisoformat(since_date) - timedelta(days=1)).strftime("%Y-%m-%d")
        prev = conn.execute(
            "SELECT ctl, atl FROM daily_metrics WHERE date = %s", (prev_day,)
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
    day_list = []
    tss_list = []
    while day <= end:
        ds = day.strftime("%Y-%m-%d")
        day_list.append(ds)
        tss_list.append(daily_tss.get(ds, 0.0))
        day += timedelta(days=1)

    # Vectorized calculation
    from server.metrics import calculate_pmc
    ctl_values, atl_values = calculate_pmc(tss_list, initial_ctl=ctl, initial_atl=atl)

    pmc_rows = []
    for i, ds in enumerate(day_list):
        tss = tss_list[i]
        c = ctl_values[i]
        a = atl_values[i]
        tsb = c - a
        
        # Determine weight and FTP for this day
        # Preference: 
        # 1. most recent ride on or before this day (Performance Truth)
        # 2. athlete_settings active on this day (Manual Truth)
        # 3. Defaults
        
        weight = _lookup_ride_metric(ds, weight_values)
        if weight is None or weight <= 0:
            weight = _lookup_setting_metric(ds, weight_settings)
        if weight is None or weight <= 0:
            from server.database import ATHLETE_SETTINGS_DEFAULTS
            weight = float(ATHLETE_SETTINGS_DEFAULTS.get("weight_kg", 0))
            
        ftp = _lookup_ride_metric(ds, ftp_values)
        if ftp is None or ftp <= 0:
            ftp = _lookup_setting_metric(ds, ftp_settings)
        if ftp is None or ftp <= 0:
            from server.database import ATHLETE_SETTINGS_DEFAULTS
            ftp = float(ATHLETE_SETTINGS_DEFAULTS.get("ftp", 0))

        pmc_rows.append((ds, round(tss, 1), round(c, 1), round(a, 1), round(tsb, 1), weight, ftp))

    # Batch upsert all rows
    conn.executemany(
        "INSERT INTO daily_metrics (date, total_tss, ctl, atl, tsb, weight, ftp) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (date) DO UPDATE SET "
        "total_tss = EXCLUDED.total_tss, ctl = EXCLUDED.ctl, "
        "atl = EXCLUDED.atl, tsb = EXCLUDED.tsb, weight = EXCLUDED.weight, ftp = EXCLUDED.ftp",
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


def sync_athlete_settings_from_latest_ride(conn):
    """Update active athlete_settings to match benchmarks from the most recent ride."""
    # Get the most recent ride with FTP and Weight
    row = conn.execute(
        "SELECT date, ftp, weight FROM rides WHERE ftp > 0 AND weight > 0 ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row:
        from server.database import set_athlete_setting, get_athlete_setting
        
        current_ftp = get_athlete_setting("ftp")
        current_weight = get_athlete_setting("weight_kg")
        
        new_ftp = str(int(row["ftp"]))
        new_weight = str(round(row["weight"], 2))
        
        if new_ftp != current_ftp:
            logger.info("Auto-syncing FTP from latest ride: %s -> %s", current_ftp, new_ftp)
            set_athlete_setting("ftp", new_ftp, date_set=row["date"])
            
        if new_weight != current_weight:
            logger.info("Auto-syncing weight from latest ride: %s -> %s", current_weight, new_weight)
            set_athlete_setting("weight_kg", new_weight, date_set=row["date"])


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
        ride, records, power_bests, laps = parse_ride_json(filepath, conn=conn)

        if ride is None:
            continue

        cursor = conn.execute(
            """INSERT INTO rides (date, start_time, filename, sport, sub_sport, duration_s, distance_m,
               avg_power, normalized_power, max_power, avg_hr, max_hr, avg_cadence,
               total_ascent, total_descent, total_calories, tss, intensity_factor,
               ftp, total_work_kj, training_effect, variability_index,
               best_1min_power, best_5min_power, best_20min_power, best_60min_power,
               weight, start_lat, start_lon, has_power_data, data_status)
            VALUES (:date, :start_time, :filename, :sport, :sub_sport, :duration_s, :distance_m,
               :avg_power, :normalized_power, :max_power, :avg_hr, :max_hr, :avg_cadence,
               :total_ascent, :total_descent, :total_calories, :tss, :intensity_factor,
               :ftp, :total_work_kj, :training_effect, :variability_index,
               :best_1min_power, :best_5min_power, :best_20min_power, :best_60min_power,
               :weight, :start_lat, :start_lon, :has_power_data, :data_status) RETURNING id""",
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
                "INSERT INTO power_bests (ride_id, date, duration_s, power, avg_hr, avg_cadence, start_offset_s) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(ride_id, ride["date"], pb["duration_s"], pb["power"], pb.get("avg_hr"), pb.get("avg_cadence"), pb.get("start_offset_s")) for pb in power_bests],
            )

        # Insert laps
        if laps:
            conn.executemany(
                """INSERT INTO ride_laps (ride_id, lap_index, start_time, total_timer_time,
                   total_elapsed_time, total_distance, avg_power, normalized_power, max_power,
                   avg_hr, max_hr, avg_cadence, max_cadence, avg_speed, max_speed,
                   total_ascent, total_descent, total_calories, total_work,
                   intensity, lap_trigger, wkt_step_index,
                   start_lat, start_lon, end_lat, end_lon, avg_temperature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(ride_id, l["lap_index"], l["start_time"], l["total_timer_time"],
                  l["total_elapsed_time"], l["total_distance"], l["avg_power"], l["normalized_power"], l["max_power"],
                  l["avg_hr"], l["max_hr"], l["avg_cadence"], l["max_cadence"], l["avg_speed"], l["max_speed"],
                  l["total_ascent"], l["total_descent"], l["total_calories"], l["total_work"],
                  l["intensity"], l["lap_trigger"], l["wkt_step_index"],
                  l["start_lat"], l["start_lon"], l["end_lat"], l["end_lon"], l["avg_temperature"])
                 for l in laps],
            )

        ingested += 1

    if ingested > 0:
        sync_athlete_settings_from_latest_ride(conn)

    return ingested


def backfill_laps(conn, rides_dir=None):
    """Backfill lap data for rides ingested before lap support."""
    rides_dir = rides_dir or RIDES_DIR
    rides_with_laps = set(
        r["ride_id"] for r in conn.execute("SELECT DISTINCT ride_id FROM ride_laps").fetchall()
    )
    all_rides = conn.execute("SELECT id, filename FROM rides").fetchall()
    backfilled = 0
    for ride_row in all_rides:
        if ride_row["id"] in rides_with_laps:
            continue
        filepath = os.path.join(rides_dir, ride_row["filename"])
        if not os.path.exists(filepath):
            continue
        _ride, _records, _power_bests, laps = parse_ride_json(filepath, conn=conn)
        if not laps:
            continue
        conn.executemany(
            """INSERT INTO ride_laps (ride_id, lap_index, start_time, total_timer_time,
               total_elapsed_time, total_distance, avg_power, normalized_power, max_power,
               avg_hr, max_hr, avg_cadence, max_cadence, avg_speed, max_speed,
               total_ascent, total_descent, total_calories, total_work,
               intensity, lap_trigger, wkt_step_index,
               start_lat, start_lon, end_lat, end_lon, avg_temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(ride_row["id"], l["lap_index"], l["start_time"], l["total_timer_time"],
              l["total_elapsed_time"], l["total_distance"], l["avg_power"], l["normalized_power"], l["max_power"],
              l["avg_hr"], l["max_hr"], l["avg_cadence"], l["max_cadence"], l["avg_speed"], l["max_speed"],
              l["total_ascent"], l["total_descent"], l["total_calories"], l["total_work"],
              l["intensity"], l["lap_trigger"], l["wkt_step_index"],
              l["start_lat"], l["start_lon"], l["end_lat"], l["end_lon"], l["avg_temperature"])
             for l in laps],
        )
        backfilled += 1
    logger.info("Backfilled laps for %d rides", backfilled)
    return backfilled


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

        logger.info("Backfilling laps...")
        backfill_laps(conn)

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
