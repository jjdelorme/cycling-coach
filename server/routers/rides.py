"""Ride data endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from server.auth import CurrentUser, require_read, require_write
from server.database import get_db
from server.models.schemas import RideSummary, RideDetail, RideRecord, RideLap, WeeklySummary, MonthlySummary, DailySummary
from server.ingest import compute_daily_pmc


class RideCommentsUpdate(BaseModel):
    post_ride_comments: Optional[str] = None


class RideTitleUpdate(BaseModel):
    title: Optional[str] = None

router = APIRouter(prefix="/api/rides", tags=["rides"])


@router.get("", response_model=list[RideSummary])
def list_rides(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    sport: Optional[str] = Query(None),
    limit: int = Query(500),
    user: CurrentUser = Depends(require_read),
):
    query = "SELECT * FROM rides WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    if sport:
        query += " AND (sport = %s OR sub_sport = %s)"
        params.extend([sport, sport])
    query += " ORDER BY date DESC LIMIT %s"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [RideSummary(**dict(r)) for r in rows]


def aggregate_daily_rides(rows: list[dict], days: int = 7) -> list[DailySummary]:
    """Aggregate a list of ride dicts by date. Pure function — no DB access."""
    from collections import defaultdict
    daily: dict = defaultdict(lambda: {
        "rides": 0, "duration_s": 0.0, "tss": 0.0,
        "total_calories": 0, "distance_m": 0.0, "ascent_m": 0,
        "_power_x_dur": 0.0, "_powered_dur": 0.0,
    })
    for r in rows:
        d = r.get("date", "")
        if not d:
            continue
        dur = r.get("duration_s") or 0
        daily[d]["rides"] += 1
        daily[d]["duration_s"] += dur
        daily[d]["tss"] += r.get("tss") or 0
        daily[d]["total_calories"] += r.get("total_calories") or 0
        daily[d]["distance_m"] += r.get("distance_m") or 0
        daily[d]["ascent_m"] += r.get("total_ascent") or 0
        pwr = r.get("avg_power") or 0
        if pwr > 0 and dur > 0:
            daily[d]["_power_x_dur"] += pwr * dur
            daily[d]["_powered_dur"] += dur
    result = []
    for date in sorted(daily):
        v = daily[date]
        avg_power = round(v["_power_x_dur"] / v["_powered_dur"]) if v["_powered_dur"] > 0 else None
        result.append(DailySummary(
            date=date, rides=v["rides"], duration_s=v["duration_s"],
            tss=v["tss"], total_calories=v["total_calories"],
            distance_m=v["distance_m"], ascent_m=v["ascent_m"],
            avg_power=avg_power,
        ))
    return result


@router.get("/summary/daily", response_model=list[DailySummary])
def daily_summary(
    days: int = Query(7, ge=1, le=90),
    user: CurrentUser = Depends(require_read),
):
    from datetime import date as dt_date, timedelta
    since = (dt_date.today() - timedelta(days=days - 1)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT date, duration_s, tss, total_calories, distance_m, total_ascent, avg_power FROM rides WHERE date >= %s ORDER BY date",
            (since,),
        ).fetchall()
    return aggregate_daily_rides([dict(r) for r in rows], days=days)


@router.get("/summary/weekly", response_model=list[WeeklySummary])
def weekly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    from datetime import date as dt_date
    query = """
        SELECT date, duration_s, tss, distance_m, total_ascent, avg_power, avg_hr, best_20min_power
        FROM rides WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    query += " ORDER BY date"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    from collections import defaultdict
    weeks = defaultdict(lambda: {"rides": 0, "duration_s": 0, "tss": 0, "distance_m": 0, "ascent_m": 0, "powers": [], "hrs": [], "best_20min": 0})
    for r in rows:
        d = dict(r)
        parsed = dt_date.fromisoformat(d["date"])
        iso = parsed.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        w = weeks[week_key]
        w["rides"] += 1
        w["duration_s"] += d["duration_s"] or 0
        w["tss"] += d["tss"] or 0
        w["distance_m"] += d["distance_m"] or 0
        w["ascent_m"] += d["total_ascent"] or 0
        if d["avg_power"] and d["avg_power"] > 0:
            w["powers"].append(d["avg_power"])
        if d["avg_hr"] and d["avg_hr"] > 0:
            w["hrs"].append(d["avg_hr"])
        w["best_20min"] = max(w["best_20min"], d["best_20min_power"] or 0)

    result = []
    for week_key in sorted(weeks):
        w = weeks[week_key]
        result.append(WeeklySummary(
            week=week_key,
            rides=w["rides"],
            duration_h=round(w["duration_s"] / 3600.0, 1),
            tss=round(w["tss"], 1),
            distance_km=round(w["distance_m"] / 1000.0, 1),
            ascent_m=int(w["ascent_m"]),
            avg_power=round(sum(w["powers"]) / len(w["powers"])) if w["powers"] else None,
            avg_hr=round(sum(w["hrs"]) / len(w["hrs"])) if w["hrs"] else None,
            best_20min=w["best_20min"] or None,
        ))
    return result


@router.get("/summary/monthly", response_model=list[MonthlySummary])
def monthly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
):
    query = """
        SELECT
            SUBSTR(date, 1, 7) as month,
            COUNT(*) as rides,
            ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as duration_h,
            ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 1) as tss,
            ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 1) as distance_km,
            CAST(SUM(COALESCE(total_ascent, 0)) AS INTEGER) as ascent_m,
            ROUND(CAST(AVG(CASE WHEN avg_power > 0 THEN avg_power END) AS NUMERIC), 0) as avg_power,
            ROUND(CAST(AVG(CASE WHEN avg_hr > 0 THEN avg_hr END) AS NUMERIC), 0) as avg_hr,
            MAX(best_20min_power) as best_20min
        FROM rides
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    query += " GROUP BY month ORDER BY month"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [MonthlySummary(**dict(r)) for r in rows]


@router.get("/{ride_id}", response_model=RideDetail)
def get_ride(ride_id: int, user: CurrentUser = Depends(require_read)):
    with get_db() as conn:
        ride = conn.execute("SELECT * FROM rides WHERE id = %s", (ride_id,)).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        records = conn.execute(
            "SELECT timestamp_utc, power, heart_rate, cadence, speed, altitude, distance, lat, lon, temperature FROM ride_records WHERE ride_id = %s ORDER BY id",
            (ride_id,),
        ).fetchall()

        laps = conn.execute(
            "SELECT * FROM ride_laps WHERE ride_id = %s ORDER BY lap_index",
            (ride_id,),
        ).fetchall()

    return RideDetail(
        **dict(ride),
        records=[RideRecord(**dict(r)) for r in records],
        laps=[RideLap(**{k: v for k, v in dict(l).items() if k not in ("id", "ride_id")}) for l in laps],
    )


@router.put("/{ride_id}/comments")
def update_ride_comments(ride_id: int, body: RideCommentsUpdate, user: CurrentUser = Depends(require_write)):
    with get_db() as conn:
        ride = conn.execute("SELECT id FROM rides WHERE id = %s", (ride_id,)).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")
        conn.execute(
            "UPDATE rides SET post_ride_comments = %s WHERE id = %s",
            (body.post_ride_comments, ride_id),
        )
    return {"status": "ok"}


@router.put("/{ride_id}/title")
def update_ride_title(ride_id: int, body: RideTitleUpdate, user: CurrentUser = Depends(require_write)):
    with get_db() as conn:
        ride = conn.execute("SELECT id FROM rides WHERE id = %s", (ride_id,)).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")
        conn.execute(
            "UPDATE rides SET title = %s WHERE id = %s",
            (body.title, ride_id),
        )
    return {"status": "ok"}


@router.delete("/{ride_id}")
def delete_ride(ride_id: int, user: CurrentUser = Depends(require_write)):
    with get_db() as conn:
        # 1. Get ride date for PMC recalculation
        ride = conn.execute("SELECT date FROM rides WHERE id = %s", (ride_id,)).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        ride_date = ride["date"]

        # 2. Delete dependencies
        conn.execute("DELETE FROM ride_records WHERE ride_id = %s", (ride_id,))
        conn.execute("DELETE FROM ride_laps WHERE ride_id = %s", (ride_id,))
        conn.execute("DELETE FROM power_bests WHERE ride_id = %s", (ride_id,))

        # 3. Delete ride
        conn.execute("DELETE FROM rides WHERE id = %s", (ride_id,))

        # 4. Recalculate PMC
        compute_daily_pmc(conn, since_date=ride_date)

    return {"status": "ok"}
