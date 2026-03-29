"""ADK tools for the coaching agent to query training data."""

import math
from datetime import datetime, timedelta
from server.database import get_db, get_athlete_setting
from server.queries import get_current_pmc_row, get_pmc_row_for_date, get_power_bests_rows, get_ftp_history_rows, get_periodization_phases


# ---------------------------------------------------------------------------
# Helpers (not tools)
# ---------------------------------------------------------------------------

_DURATION_LABELS = {5: "5s", 30: "30s", 60: "1min", 300: "5min", 1200: "20min", 3600: "60min"}
_BEST_EFFORT_DURATIONS = [5, 30, 60, 300, 1200, 3600]


def _resolve_ride_id(conn, date: str):
    """Resolve a YYYY-MM-DD date to a ride_id (longest ride on that date)."""
    row = conn.execute(
        "SELECT id, date, duration_s FROM rides WHERE date = ? ORDER BY duration_s DESC LIMIT 1",
        (date,),
    ).fetchone()
    if not row:
        return None, f"No ride found for date {date}"
    return row["id"], row["date"]


def _compute_rolling_best_with_index(values: list, window_s: int):
    """Sliding window best average with start index tracking.
    Returns (best_avg, start_index) or None.
    """
    clean = [v if v is not None else 0 for v in values]
    if len(clean) < window_s:
        return None
    current_sum = sum(clean[:window_s])
    best_sum = current_sum
    best_start = 0
    for i in range(window_s, len(clean)):
        current_sum += clean[i] - clean[i - window_s]
        if current_sum > best_sum:
            best_sum = current_sum
            best_start = i - window_s + 1
    return round(best_sum / window_s), best_start


def _compute_power_zones(powers: list, ftp: int) -> dict:
    """Compute power zone distribution matching server/routers/analysis.py."""
    zone_defs = [
        ("Z1", "Active Recovery", "<55%", 0, 0.55),
        ("Z2", "Endurance", "55-75%", 0.55, 0.75),
        ("Z3", "Tempo", "75-90%", 0.75, 0.90),
        ("Z4", "Threshold", "90-105%", 0.90, 1.05),
        ("Z5", "VO2max", "105-120%", 1.05, 1.20),
        ("Z6", "Anaerobic", ">120%", 1.20, float("inf")),
    ]
    counts = {z[0]: 0 for z in zone_defs}
    coasting = 0
    total = 0
    for p in powers:
        if p is None or p == 0:
            coasting += 1
            continue
        total += 1
        for name, _, _, lo, hi in zone_defs:
            if ftp * lo <= p < ftp * hi:
                counts[name] += 1
                break

    zones = []
    for name, label, rng, _, _ in zone_defs:
        secs = counts[name]
        pct = round(100 * secs / total, 1) if total > 0 else 0
        zones.append({"zone": name, "label": label, "range": rng, "seconds": secs, "pct": pct})

    return {"ftp_used": ftp, "zones": zones, "coasting_seconds": coasting}


def _compute_hr_zones(heart_rates: list, lthr: int) -> dict | None:
    """Compute HR zone distribution."""
    if not lthr or lthr <= 0:
        return None
    zone_defs = [
        ("Z1", "Recovery", "<81%", 0, 0.81),
        ("Z2", "Aerobic", "81-89%", 0.81, 0.89),
        ("Z3", "Tempo", "89-93%", 0.89, 0.93),
        ("Z4", "Threshold", "93-99%", 0.93, 0.99),
        ("Z5", "VO2max", ">99%", 0.99, float("inf")),
    ]
    counts = {z[0]: 0 for z in zone_defs}
    total = 0
    for hr in heart_rates:
        if hr is None or hr == 0:
            continue
        total += 1
        for name, _, _, lo, hi in zone_defs:
            if lthr * lo <= hr < lthr * hi:
                counts[name] += 1
                break

    if total == 0:
        return None

    zones = []
    for name, label, rng, _, _ in zone_defs:
        secs = counts[name]
        pct = round(100 * secs / total, 1) if total > 0 else 0
        zones.append({"zone": name, "label": label, "range": rng, "seconds": secs, "pct": pct})
    return {"lthr_used": lthr, "zones": zones}


def _compute_hr_drift(powers: list, heart_rates: list) -> dict | None:
    """Compute HR drift between first and second half of ride."""
    valid = [(p, hr) for p, hr in zip(powers, heart_rates)
             if p is not None and p > 0 and hr is not None and hr > 0]
    if len(valid) < 600:
        return None
    mid = len(valid) // 2
    first_hr = sum(hr for _, hr in valid[:mid]) / mid
    second_hr = sum(hr for _, hr in valid[mid:]) / (len(valid) - mid)
    drift = round(100 * (second_hr - first_hr) / first_hr, 1) if first_hr > 0 else 0
    return {
        "first_half_avg_hr": round(first_hr, 1),
        "second_half_avg_hr": round(second_hr, 1),
        "drift_pct": drift,
    }


def _compute_np(powers: list) -> float | None:
    """Compute Normalized Power using Coggan formula (30s rolling avg, 4th power)."""
    clean = [p if p is not None else 0 for p in powers]
    if len(clean) < 30:
        return None
    rolling = []
    window_sum = sum(clean[:30])
    for i in range(30, len(clean)):
        rolling.append(window_sum / 30)
        window_sum += clean[i] - clean[i - 30]
    rolling.append(window_sum / 30)
    if not rolling:
        return None
    avg_4th = sum(v ** 4 for v in rolling) / len(rolling)
    return round(avg_4th ** 0.25, 1)


def _compute_decoupling(powers: list, heart_rates: list) -> dict | None:
    """Compute aerobic decoupling (Pw:Hr ratio first vs second half)."""
    valid_p = []
    valid_hr = []
    for p, hr in zip(powers, heart_rates):
        if p is not None and p > 0 and hr is not None and hr > 0:
            valid_p.append(p)
            valid_hr.append(hr)
    if len(valid_p) < 1200:
        return None
    mid = len(valid_p) // 2
    np1 = _compute_np(valid_p[:mid])
    np2 = _compute_np(valid_p[mid:])
    hr1 = sum(valid_hr[:mid]) / mid
    hr2 = sum(valid_hr[mid:]) / (len(valid_hr) - mid)
    if not np1 or not np2 or hr1 <= 0 or hr2 <= 0:
        return None
    ratio1 = np1 / hr1
    ratio2 = np2 / hr2
    decoupling = round(100 * (ratio1 - ratio2) / ratio1, 1) if ratio1 > 0 else 0
    return {
        "first_half_np_hr": round(ratio1, 3),
        "second_half_np_hr": round(ratio2, 3),
        "decoupling_pct": decoupling,
    }


def get_pmc_metrics(date: str = "") -> dict:
    """Get current fitness metrics (CTL, ATL, TSB) for a given date or today.

    Args:
        date: Date string (YYYY-MM-DD). Defaults to most recent available.

    Returns:
        Dictionary with ctl (fitness), atl (fatigue), tsb (form), weight.
    """
    with get_db() as conn:
        row = get_pmc_row_for_date(conn, date) if date else get_current_pmc_row(conn)

    if not row:
        return {"error": "No PMC data found"}

    return {
        "date": row["date"],
        "ctl": row["ctl"],
        "atl": row["atl"],
        "tsb": row["tsb"],
        "weight": row["weight"],
    }


def get_recent_rides(days_back: int = 7) -> list[dict]:
    """Get summary of recent completed rides.

    Args:
        days_back: Number of days to look back. Default 7.

    Returns:
        List of ride summaries with date, sport, duration, TSS, power, HR.
    """
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, date, sub_sport, duration_s, distance_m, tss, avg_power,
                      normalized_power, avg_hr, total_ascent, best_20min_power,
                      post_ride_comments, coach_comments
               FROM rides WHERE date >= ? ORDER BY date DESC""",
            (cutoff,),
        ).fetchall()

    return [
        {
            "ride_id": r["id"],
            "date": r["date"],
            "sport": r["sub_sport"],
            "duration_h": round((r["duration_s"] or 0) / 3600, 1),
            "distance_km": round((r["distance_m"] or 0) / 1000, 1),
            "tss": r["tss"],
            "avg_power": r["avg_power"],
            "normalized_power": r["normalized_power"],
            "avg_hr": r["avg_hr"],
            "ascent_m": r["total_ascent"],
            "best_20min": r["best_20min_power"],
            "athlete_post_ride_notes": r["post_ride_comments"],
            "coach_post_ride_notes": r["coach_comments"],
        }
        for r in rows
    ]


def get_upcoming_workouts(days_ahead: int = 7) -> list[dict]:
    """Get planned workouts for the coming days.

    Args:
        days_ahead: Number of days to look ahead. Default 7.

    Returns:
        List of planned workouts with date, name, duration.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, name, sport, total_duration_s, coach_notes, athlete_notes FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (today, end),
        ).fetchall()

    return [
        {
            "date": r["date"],
            "name": r["name"],
            "sport": r["sport"],
            "duration_min": round((r["total_duration_s"] or 0) / 60),
            "coach_notes": r["coach_notes"],
            "athlete_notes": r["athlete_notes"],
        }
        for r in rows
    ]


def get_power_bests() -> dict:
    """Get all-time best power outputs at standard durations.

    Returns:
        Dictionary mapping duration labels to best power and date.
    """
    labels = {5: "5s", 30: "30s", 60: "1min", 300: "5min", 1200: "20min", 3600: "60min"}

    with get_db() as conn:
        rows = get_power_bests_rows(conn)

    return {
        labels.get(r["duration_s"], f"{r['duration_s']}s"): {"power": r["power"], "date": r["date"]}
        for r in rows
    }


def get_training_summary(period: str = "month") -> dict:
    """Get training volume summary for a period.

    Args:
        period: 'week', 'month', or 'season' for the summary period.

    Returns:
        Summary with ride count, hours, TSS, distance.
    """
    if period == "week":
        days = 7
    elif period == "month":
        days = 30
    else:
        days = 365

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as rides,
                      ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as hours,
                      ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 0) as tss,
                      ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 0) as distance_km,
                      ROUND(CAST(SUM(COALESCE(total_ascent, 0)) AS NUMERIC), 0) as ascent_m
               FROM rides WHERE date >= ?""",
            (cutoff,),
        ).fetchone()

    return {
        "period": period,
        "rides": row["rides"],
        "hours": row["hours"],
        "tss": row["tss"],
        "distance_km": row["distance_km"],
        "ascent_m": row["ascent_m"],
    }


def get_ftp_history() -> list[dict]:
    """Get FTP progression over time by month, including current athlete setting.

    Returns:
        List of monthly FTP values with W/kg.
    """
    with get_db() as conn:
        rows = get_ftp_history_rows(conn)

    return [
        {
            "month": r["month"],
            "ftp": r["ftp"],
            "weight_kg": r["weight"],
            "w_per_kg": r["w_per_kg"],
            **({"source": r["source"]} if "source" in r else {}),
        }
        for r in rows
    ]


def get_periodization_status() -> dict:
    """Get the current training periodization phase and schedule.

    Returns:
        Current phase info and all phases with dates.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        phases = get_periodization_phases(conn)

    all_phases = []
    current = None
    for p in phases:
        phase = {
            "id": p["id"],
            "name": p["name"],
            "start_date": p["start_date"],
            "end_date": p["end_date"],
            "focus": p["focus"],
            "hours_per_week": f"{p['hours_per_week_low']}-{p['hours_per_week_high']}",
            "tss_target": f"{p['tss_target_low']}-{p['tss_target_high']}",
        }
        all_phases.append(phase)
        if p["start_date"] <= today <= p["end_date"]:
            current = phase

    return {
        "current_phase": current or {"name": "Off-season", "focus": "Recovery and base maintenance"},
        "all_phases": all_phases,
    }


def get_ride_analysis(date: str) -> dict:
    """Get computed analysis metrics for a ride on a given date.

    Computes best efforts at standard durations (with start offset), zone distribution,
    HR drift, fatigue decoupling, and other derived metrics. This performs server-side
    computation over ride_records so the agent gets summarized insights without raw data.

    Args:
        date: Date string (YYYY-MM-DD) of the ride to analyze.

    Returns:
        Dictionary with best_efforts, power_zones, hr_zones, metrics, and warnings.
    """
    with get_db() as conn:
        ride_id, date_or_err = _resolve_ride_id(conn, date)
        if ride_id is None:
            return {"error": date_or_err}

        ride = conn.execute(
            "SELECT duration_s, avg_power, normalized_power, avg_hr, avg_cadence, ftp, intensity_factor FROM rides WHERE id = ?",
            (ride_id,),
        ).fetchone()

        rows = conn.execute(
            "SELECT power, heart_rate, cadence, speed, altitude FROM ride_records WHERE ride_id = ? ORDER BY id",
            (ride_id,),
        ).fetchall()

        # All-time bests for comparison
        alltime = get_power_bests_rows(conn)
        alltime_map = {r["duration_s"]: r["power"] for r in alltime}

    powers = [r["power"] for r in rows]
    heart_rates = [r["heart_rate"] for r in rows]
    cadences = [r["cadence"] for r in rows]

    has_power = any(p is not None and p > 0 for p in powers)
    has_hr = any(hr is not None and hr > 0 for hr in heart_rates)
    warnings = []

    if not has_power:
        warnings.append("No power data available for this ride")
    duration_s = ride["duration_s"] or 0
    if duration_s < 300:
        warnings.append("Short ride (< 5 min) — limited analysis available")

    # FTP: from ride first, fallback to athlete settings
    ftp = ride["ftp"] or 0
    if ftp == 0:
        try:
            ftp = int(get_athlete_setting("ftp") or 0)
        except (ValueError, TypeError):
            ftp = 0

    # Best efforts
    best_efforts = []
    if has_power:
        for dur_s in _BEST_EFFORT_DURATIONS:
            if len(powers) < dur_s:
                continue
            result = _compute_rolling_best_with_index(powers, dur_s)
            if result is None:
                continue
            avg_power, start_idx = result
            # Average HR and cadence for the best effort window
            window_hrs = [hr for hr in heart_rates[start_idx:start_idx + dur_s] if hr is not None and hr > 0]
            window_cads = [c for c in cadences[start_idx:start_idx + dur_s] if c is not None and c > 0]
            alltime_best = alltime_map.get(dur_s)
            pct_of_alltime = round(100 * avg_power / alltime_best, 1) if alltime_best and alltime_best > 0 else None
            best_efforts.append({
                "duration": _DURATION_LABELS.get(dur_s, f"{dur_s}s"),
                "duration_s": dur_s,
                "avg_power": avg_power,
                "start_offset_s": start_idx,
                "avg_hr": round(sum(window_hrs) / len(window_hrs)) if window_hrs else None,
                "avg_cadence": round(sum(window_cads) / len(window_cads)) if window_cads else None,
                "pct_of_alltime": pct_of_alltime,
            })

    # Power zones
    power_zones = None
    if has_power and ftp > 0:
        power_zones = _compute_power_zones(powers, ftp)
    elif has_power and ftp == 0:
        warnings.append("FTP is 0 — cannot compute power zones")

    # HR zones
    hr_zones = None
    if has_hr:
        try:
            lthr = int(get_athlete_setting("lthr") or 0)
        except (ValueError, TypeError):
            lthr = 0
        if lthr > 0:
            hr_zones = _compute_hr_zones(heart_rates, lthr)

    # Metrics
    np_val = ride["normalized_power"]
    avg_p = ride["avg_power"]
    avg_hr_val = ride["avg_hr"]
    vi = round(np_val / avg_p, 3) if np_val and avg_p and avg_p > 0 else None
    if_val = round(np_val / ftp, 3) if np_val and ftp and ftp > 0 else ride["intensity_factor"]
    ef = round(np_val / avg_hr_val, 3) if np_val and avg_hr_val and avg_hr_val > 0 else None

    # HR drift and decoupling
    hr_drift = _compute_hr_drift(powers, heart_rates) if has_power and has_hr else None
    decoupling = _compute_decoupling(powers, heart_rates) if has_power and has_hr else None

    return {
        "ride_id": ride_id,
        "date": date_or_err,
        "duration_s": duration_s,
        "record_count": len(rows),
        "has_power": has_power,
        "best_efforts": best_efforts,
        "power_zones": power_zones,
        "hr_zones": hr_zones,
        "metrics": {
            "variability_index": vi,
            "intensity_factor": if_val,
            "efficiency_factor": ef,
            "avg_power": avg_p,
            "normalized_power": np_val,
            "avg_hr": avg_hr_val,
            "avg_cadence": ride["avg_cadence"],
        },
        "hr_drift": hr_drift,
        "decoupling": decoupling,
        "warnings": warnings,
    }


def get_ride_segments(date: str, segment_duration_s: int = 300) -> dict:
    """Get a ride's data as averaged time segments for trend analysis.

    Downsamples per-second data into segments (default 5-minute windows).

    Args:
        date: Date string (YYYY-MM-DD).
        segment_duration_s: Window size in seconds (min 60, max 1800).

    Returns:
        Dictionary with segments containing averaged metrics per window.
    """
    segment_duration_s = max(60, min(1800, segment_duration_s))

    with get_db() as conn:
        ride_id, date_or_err = _resolve_ride_id(conn, date)
        if ride_id is None:
            return {"error": date_or_err}

        rows = conn.execute(
            "SELECT power, heart_rate, cadence, speed, altitude, distance FROM ride_records WHERE ride_id = ? ORDER BY id",
            (ride_id,),
        ).fetchall()

    if not rows:
        return {"error": f"No records found for ride on {date}"}

    segments = []
    for chunk_start in range(0, len(rows), segment_duration_s):
        chunk = rows[chunk_start:chunk_start + segment_duration_s]

        powers = [r["power"] for r in chunk if r["power"] is not None and r["power"] > 0]
        hrs = [r["heart_rate"] for r in chunk if r["heart_rate"] is not None and r["heart_rate"] > 0]
        cads = [r["cadence"] for r in chunk if r["cadence"] is not None and r["cadence"] > 0]
        speeds = [r["speed"] for r in chunk if r["speed"] is not None and r["speed"] > 0]
        alts = [r["altitude"] for r in chunk if r["altitude"] is not None]
        dists = [r["distance"] for r in chunk if r["distance"] is not None]

        # Altitude gain from positive deltas
        alt_gain = 0.0
        if len(alts) > 1:
            for i in range(1, len(alts)):
                delta = alts[i] - alts[i - 1]
                if delta > 0:
                    alt_gain += delta

        # Distance for this segment
        seg_distance = None
        if len(dists) >= 2:
            seg_distance = round(dists[-1] - dists[0], 1)

        segments.append({
            "segment": len(segments) + 1,
            "start_elapsed_s": chunk_start,
            "avg_power": round(sum(powers) / len(powers)) if powers else None,
            "max_power": max(powers) if powers else None,
            "min_power": min(powers) if powers else None,
            "avg_hr": round(sum(hrs) / len(hrs)) if hrs else None,
            "max_hr": max(hrs) if hrs else None,
            "avg_cadence": round(sum(cads) / len(cads)) if cads else None,
            "avg_speed_kph": round(sum(speeds) / len(speeds) * 3.6, 1) if speeds else None,
            "altitude_gain_m": round(alt_gain, 1) if alt_gain > 0 else None,
            "distance_m": seg_distance,
        })

    return {
        "ride_id": ride_id,
        "date": date_or_err,
        "segment_duration_s": segment_duration_s,
        "segment_count": len(segments),
        "segments": segments,
    }


def get_ride_records_window(date: str, start_s: int = 0, end_s: int = 300) -> dict:
    """Get raw per-second ride data for a specific time window (max 600 seconds).

    Use get_ride_analysis or get_ride_segments first to identify interesting windows,
    then drill into specific intervals with this tool.

    Args:
        date: Date string (YYYY-MM-DD).
        start_s: Start offset in seconds from ride start.
        end_s: End offset in seconds from ride start.

    Returns:
        Dictionary with per-second records for the requested window.
    """
    start_s = max(0, start_s)
    end_s = min(end_s, start_s + 600)
    if end_s <= start_s:
        return {"error": "end_s must be greater than start_s"}

    window_size = end_s - start_s

    with get_db() as conn:
        ride_id, date_or_err = _resolve_ride_id(conn, date)
        if ride_id is None:
            return {"error": date_or_err}

        rows = conn.execute(
            "SELECT power, heart_rate, cadence, speed, altitude FROM ride_records WHERE ride_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (ride_id, window_size, start_s),
        ).fetchall()

    records = []
    for i, r in enumerate(rows):
        records.append({
            "elapsed_s": start_s + i,
            "power": r["power"],
            "heart_rate": r["heart_rate"],
            "cadence": r["cadence"],
            "speed_kph": round(r["speed"] * 3.6, 1) if r["speed"] is not None else None,
            "altitude_m": r["altitude"],
        })

    return {
        "ride_id": ride_id,
        "date": date_or_err,
        "window_start_s": start_s,
        "window_end_s": start_s + len(records),
        "record_count": len(records),
        "records": records,
    }


def get_power_curve(start_date: str = "", end_date: str = "", last_n_days: int = 0) -> dict:
    """Get best power outputs across rides for a date range.

    Queries pre-computed power_bests table for peak power at standard durations.

    Args:
        start_date: Start date (YYYY-MM-DD). Ignored if last_n_days > 0.
        end_date: End date (YYYY-MM-DD). Ignored if last_n_days > 0.
        last_n_days: If > 0, use last N days ending today.

    Returns:
        Dictionary with best power at each standard duration.
    """
    if last_n_days > 0:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=last_n_days)).strftime("%Y-%m-%d")
    elif not start_date and not end_date:
        start_date = None
        end_date = None
    else:
        if not start_date:
            start_date = None
        if not end_date:
            end_date = None

    with get_db() as conn:
        rows = get_power_bests_rows(conn, start_date, end_date)

    bests = []
    seen_durations = set()
    for r in rows:
        dur = r["duration_s"]
        if dur in seen_durations:
            continue
        seen_durations.add(dur)
        bests.append({
            "duration": _DURATION_LABELS.get(dur, f"{dur}s"),
            "duration_s": dur,
            "power": r["power"],
            "date": r["date"],
            "ride_id": r["ride_id"],
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "bests": bests,
    }
