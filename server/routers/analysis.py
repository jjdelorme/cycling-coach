"""Analysis endpoints: power curve, zones, efficiency, FTP history."""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from server.auth import CurrentUser, require_read
from server.database import get_db, get_athlete_setting
from server.models.schemas import PowerBestEntry
from server.queries import get_power_bests_rows, get_ftp_history_rows

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/power-curve")
def power_curve(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    """Best power at standard durations."""
    with get_db() as conn:
        rows = get_power_bests_rows(conn, start_date, end_date)

    return [
        {"duration_s": r["duration_s"], "power": r["power"], "avg_hr": r["avg_hr"], "date": r["date"], "ride_id": r["ride_id"]}
        for r in rows
    ]


@router.get("/power-curve/history")
def power_curve_history(user: CurrentUser = Depends(require_read)):
    """Power curve by month for tracking progression."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT SUBSTR(date, 1, 7) as month, duration_s, MAX(power) as power
            FROM power_bests
            GROUP BY month, duration_s
            ORDER BY month, duration_s
        """).fetchall()

    result = {}
    for r in rows:
        month = r["month"]
        if month not in result:
            result[month] = []
        result[month].append({"duration_s": r["duration_s"], "power": r["power"]})

    return result


@router.get("/zones")
def zone_distribution(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    """Power zone distribution from ride records."""
    query = """
        SELECT r.ftp, rr.power
        FROM ride_records rr
        JOIN rides r ON rr.ride_id = r.id
        WHERE rr.power IS NOT NULL AND rr.power > 0 AND r.ftp > 0
          AND rr.power <= 2000 AND rr.power <= (r.ftp * 5)
    """
    params = []
    if start_date:
        query += " AND r.date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND r.date <= ?"
        params.append(end_date)

    zones = {"z0": 0, "z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0, "z6": 0}
    total = 0

    with get_db() as conn:
        # Process in chunks to avoid loading 2M records into memory
        cursor = conn.execute(query, params)
        while True:
            rows = cursor.fetchmany(10000)
            if not rows:
                break
            for row in rows:
                ftp = row["ftp"]
                power = row["power"]
                total += 1
                if power == 0:
                    zones["z0"] += 1
                elif power < ftp * 0.55:
                    zones["z1"] += 1
                elif power < ftp * 0.75:
                    zones["z2"] += 1
                elif power < ftp * 0.90:
                    zones["z3"] += 1
                elif power < ftp * 1.05:
                    zones["z4"] += 1
                elif power < ftp * 1.20:
                    zones["z5"] += 1
                else:
                    zones["z6"] += 1

    if total > 0:
        percentages = {k: round(100 * v / total, 1) for k, v in zones.items()}
    else:
        percentages = zones

    return {"seconds": zones, "percentages": percentages, "total_samples": total}


@router.get("/efficiency")
def efficiency_factor(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    """Efficiency Factor (NP/avgHR) over time with 30-day rolling average.

    Filters for cycling sports and endurance rides (duration >= 30min, IF 0.5-0.8).
    """
    query = """
        SELECT id, date, normalized_power, avg_hr, duration_s, sub_sport,
               (CAST(normalized_power AS FLOAT) / avg_hr) as ef,
               AVG(CAST(normalized_power AS FLOAT) / avg_hr) OVER (
                   ORDER BY CAST(date AS DATE)
                   RANGE BETWEEN INTERVAL '30 days' PRECEDING AND CURRENT ROW
               ) as rolling_ef
        FROM rides
        WHERE normalized_power > 0 AND avg_hr > 0
          AND sport IN ('ride', 'ebikeride', 'emountainbikeride', 'gravelride',
                        'mountainbikeride', 'trackride', 'velomobile', 'virtualride',
                        'handcycle', 'cycling')
          AND duration_s >= 1800
          AND intensity_factor BETWEEN 0.5 AND 0.8
    """
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "date": r["date"],
            "ride_id": r["id"],
            "ef": round(r["ef"], 3),
            "rolling_ef": round(r["rolling_ef"], 3) if r["rolling_ef"] else None,
            "np": r["normalized_power"],
            "avg_hr": r["avg_hr"],
            "duration_s": r["duration_s"],
            "sub_sport": r["sub_sport"],
        }
        for r in rows
    ]


@router.get("/ftp-history")
def ftp_history(user: CurrentUser = Depends(require_read)):
    """FTP progression over time, including current athlete setting."""
    with get_db() as conn:
        return get_ftp_history_rows(conn)


@router.get("/route-matches")
def route_matches(ride_id: int, threshold: float = Query(0.8), user: CurrentUser = Depends(require_read)):
    """Find rides on similar routes using GPS start position proximity."""
    with get_db() as conn:
        target = conn.execute(
            "SELECT start_lat, start_lon, distance_m, total_ascent FROM rides WHERE id = ?",
            (ride_id,),
        ).fetchone()

        if not target or not target["start_lat"]:
            return []

        # Find rides starting within ~1km and similar distance/ascent
        rows = conn.execute("""
            SELECT id, date, sub_sport, duration_s, distance_m, total_ascent,
                   avg_power, normalized_power, avg_hr, tss, start_lat, start_lon
            FROM rides
            WHERE start_lat IS NOT NULL
              AND id != ?
              AND ABS(start_lat - ?) < 0.01
              AND ABS(start_lon - ?) < 0.01
            ORDER BY date
        """, (ride_id, target["start_lat"], target["start_lon"])).fetchall()

    # Filter by similar distance (within 20%)
    target_dist = target["distance_m"] or 0
    matches = []
    for r in rows:
        dist = r["distance_m"] or 0
        if target_dist > 0 and dist > 0:
            ratio = dist / target_dist
            if 0.8 <= ratio <= 1.2:
                matches.append(dict(r))

    return matches
