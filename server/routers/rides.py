"""Ride data endpoints."""

from fastapi import APIRouter, Query
from typing import Optional

from server.database import get_db
from server.models.schemas import RideSummary, RideDetail, RideRecord, WeeklySummary, MonthlySummary

router = APIRouter(prefix="/api/rides", tags=["rides"])


@router.get("", response_model=list[RideSummary])
def list_rides(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    sport: Optional[str] = Query(None),
    limit: int = Query(500),
):
    query = "SELECT * FROM rides WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if sport:
        query += " AND (sport = ? OR sub_sport = ?)"
        params.extend([sport, sport])
    query += " ORDER BY date DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [RideSummary(**dict(r)) for r in rows]


@router.get("/summary/weekly", response_model=list[WeeklySummary])
def weekly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    query = """
        SELECT
            strftime('%Y-W%W', date) as week,
            COUNT(*) as rides,
            ROUND(SUM(duration_s) / 3600.0, 1) as duration_h,
            ROUND(SUM(COALESCE(tss, 0)), 1) as tss,
            ROUND(SUM(COALESCE(distance_m, 0)) / 1000.0, 1) as distance_km,
            CAST(SUM(COALESCE(total_ascent, 0)) AS INTEGER) as ascent_m,
            ROUND(AVG(CASE WHEN avg_power > 0 THEN avg_power END), 0) as avg_power,
            ROUND(AVG(CASE WHEN avg_hr > 0 THEN avg_hr END), 0) as avg_hr,
            MAX(best_20min_power) as best_20min
        FROM rides
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY week ORDER BY week"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [WeeklySummary(**dict(r)) for r in rows]


@router.get("/summary/monthly", response_model=list[MonthlySummary])
def monthly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    query = """
        SELECT
            strftime('%Y-%m', date) as month,
            COUNT(*) as rides,
            ROUND(SUM(duration_s) / 3600.0, 1) as duration_h,
            ROUND(SUM(COALESCE(tss, 0)), 1) as tss,
            ROUND(SUM(COALESCE(distance_m, 0)) / 1000.0, 1) as distance_km,
            CAST(SUM(COALESCE(total_ascent, 0)) AS INTEGER) as ascent_m,
            ROUND(AVG(CASE WHEN avg_power > 0 THEN avg_power END), 0) as avg_power,
            ROUND(AVG(CASE WHEN avg_hr > 0 THEN avg_hr END), 0) as avg_hr,
            MAX(best_20min_power) as best_20min
        FROM rides
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY month ORDER BY month"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [MonthlySummary(**dict(r)) for r in rows]


@router.get("/{ride_id}", response_model=RideDetail)
def get_ride(ride_id: int):
    with get_db() as conn:
        ride = conn.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
        if not ride:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Ride not found")

        records = conn.execute(
            "SELECT timestamp, power, heart_rate, cadence, speed, altitude, distance, lat, lon, temperature FROM ride_records WHERE ride_id = ? ORDER BY rowid",
            (ride_id,),
        ).fetchall()

    return RideDetail(
        **dict(ride),
        records=[RideRecord(**dict(r)) for r in records],
    )
