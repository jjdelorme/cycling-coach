"""Ride data endpoints."""

from math import asin, cos, radians, sin, sqrt
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from zoneinfo import ZoneInfo

from server.auth import CurrentUser, require_read, require_write
from server.dependencies import get_client_tz
from server.database import get_db
from server.models.schemas import RideSummary, RideDetail, RideRecord, RideLap, WeeklySummary, MonthlySummary, DailySummary
from server.ingest import compute_daily_pmc
from server.services import geocoding


class RideCommentsUpdate(BaseModel):
    post_ride_comments: Optional[str] = None


class RideTitleUpdate(BaseModel):
    title: Optional[str] = None

router = APIRouter(prefix="/api/rides", tags=["rides"])


# Columns searched by the free-text `q=` filter. Order is significant for the
# generated SQL and the unit tests that assert it.
_RIDE_TEXT_SEARCH_COLUMNS = ("title", "post_ride_comments", "coach_comments")

# 1° of latitude is roughly 111.32 km everywhere on Earth. Used to convert
# the requested radius into a bounding box for the SQL prefilter.
_KM_PER_DEGREE_LAT = 111.32


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two ``(lat, lon)`` points."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return ``(min_lat, max_lat, min_lon, max_lon)`` for a radius around a point.

    Latitude span is constant (``radius_km / 111.32``); longitude span depends
    on latitude (gets wider near the equator, collapses at the poles). At
    very high latitudes ``cos(lat)`` approaches 0, so we clamp the longitude
    span at ±180° to keep the SQL bounds well-formed.
    """
    lat_delta = radius_km / _KM_PER_DEGREE_LAT
    cos_lat = max(cos(radians(lat)), 1e-6)  # guard against /0 at the poles
    lon_delta = min(radius_km / (_KM_PER_DEGREE_LAT * cos_lat), 180.0)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def _build_rides_query(
    *,
    tz_name: str,
    start_date: Optional[str],
    end_date: Optional[str],
    sport: Optional[str],
    q: Optional[str],
    limit: int,
    near: Optional[tuple[float, float]] = None,
    radius_km: Optional[float] = None,
) -> tuple[str, list]:
    """Build the SQL + params for ``GET /api/rides``.

    Pure function — no DB access, no FastAPI deps. All bind params use the
    project's ``?`` placeholder convention (translated to ``%s`` by
    ``_DbConnection._adapt_sql``). The returned SQL must NEVER inline values.

    Free-text semantics for ``q``:
    - Whitespace-trimmed; empty / whitespace-only is treated as ``None``.
    - Lowercased once, then split on whitespace into N words.
    - Each word becomes a parenthesised OR-group across the searched columns
      (currently ``title``, ``post_ride_comments``, ``coach_comments``); the N
      groups are ANDed together. So ``q="hard climb"`` requires that BOTH
      ``hard`` and ``climb`` each appear somewhere across the three columns.

    Radius semantics for ``near`` + ``radius_km``:
    - Both must be provided together. The SQL adds a bounding-box prefilter
      using the ``idx_rides_start_lat_lon`` partial index. The exact circle
      check (Haversine) is applied in Python on the returned rows so the
      SQL stays portable (no PostGIS dependency).
    - Rides with NULL ``start_lat``/``start_lon`` are silently excluded.
    """
    query = (
        "SELECT *, (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date"
        " FROM rides WHERE start_time IS NOT NULL"
    )
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE"
        params.extend([tz_name, end_date])
    if sport:
        query += " AND (sport = ? OR sub_sport = ?)"
        params.extend([sport, sport])

    if q is not None:
        words = q.strip().lower().split()
        if words:
            cols = _RIDE_TEXT_SEARCH_COLUMNS
            group = " OR ".join(f"LOWER({c}) LIKE ?" for c in cols)
            for word in words:
                like = f"%{word}%"
                query += f" AND ({group})"
                params.extend([like] * len(cols))

    if near is not None and radius_km is not None:
        lat, lon = near
        min_lat, max_lat, min_lon, max_lon = _bounding_box(lat, lon, radius_km)
        query += (
            " AND start_lat IS NOT NULL AND start_lon IS NOT NULL"
            " AND start_lat BETWEEN ? AND ?"
            " AND start_lon BETWEEN ? AND ?"
        )
        params.extend([min_lat, max_lat, min_lon, max_lon])

    query += " ORDER BY start_time DESC LIMIT ?"
    params.append(limit)
    return query, params


@router.get("", response_model=list[RideSummary])
def list_rides(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    sport: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Free-text search across title, post_ride_comments, coach_comments. Multiple words are AND-ed."),
    near: Optional[str] = Query(None, description="Place name to geocode and search around. Pair with radius_km."),
    near_lat: Optional[float] = Query(None, description="Latitude for radius search. Pair with near_lon and radius_km. Takes precedence over `near`."),
    near_lon: Optional[float] = Query(None, description="Longitude for radius search. Pair with near_lat and radius_km."),
    radius_km: Optional[float] = Query(None, ge=0.1, le=500, description="Radius in km for near/near_lat/near_lon search. Defaults to 25 if a near* param is supplied."),
    limit: int = Query(500),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)

    # ------------------------------------------------------------------
    # Resolve the radius filter inputs. The contract is:
    # - radius_km alone (no near*) is invalid (400).
    # - (near_lat AND near_lon) takes precedence over `near` so the frontend
    #   can cache geocoder results client-side and bypass the server lookup.
    # - `near` alone triggers a server-side Nominatim call, which may fail
    #   (None → 400 unresolved, exception → 503 service unavailable).
    # - radius_km defaults to 25 when any near* is present but it was omitted.
    # ------------------------------------------------------------------
    near_point: Optional[tuple[float, float]] = None
    has_explicit_coords = near_lat is not None and near_lon is not None
    has_near_query = bool(near and near.strip())

    if has_explicit_coords:
        near_point = (float(near_lat), float(near_lon))
    elif has_near_query:
        try:
            resolved = geocoding.geocode_place(near)
        except Exception as exc:  # noqa: BLE001 — translate to a 503
            raise HTTPException(
                status_code=503,
                detail="geocoding service unavailable, please try again",
            ) from exc
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"could not resolve location '{near}'",
            )
        near_point = resolved

    if radius_km is not None and near_point is None:
        raise HTTPException(
            status_code=400,
            detail="radius_km requires near or near_lat/near_lon",
        )
    if near_point is not None and radius_km is None:
        radius_km = 25.0

    query, params = _build_rides_query(
        tz_name=tz_name,
        start_date=start_date,
        end_date=end_date,
        sport=sport,
        q=q,
        limit=limit,
        near=near_point,
        radius_km=radius_km,
    )
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    summaries = [RideSummary(**dict(r)) for r in rows]

    # Bounding-box prefilter overshoots the true circle by up to ~30% on
    # the corners — apply the exact Haversine check in Python so users
    # don't see rides that are technically outside the radius.
    if near_point is not None and radius_km is not None:
        center_lat, center_lon = near_point
        summaries = [
            s for s in summaries
            if s.start_lat is not None and s.start_lon is not None
            and _haversine_km(center_lat, center_lon, s.start_lat, s.start_lon) <= radius_km
        ]

    return summaries


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
    tz: ZoneInfo = Depends(get_client_tz),
):
    from datetime import datetime, timedelta
    from server.utils.dates import user_today
    since = (datetime.fromisoformat(user_today(tz)) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    tz_name = str(tz)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date,"
            " duration_s, tss, total_calories, distance_m, total_ascent, avg_power"
            " FROM rides WHERE start_time IS NOT NULL"
            " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
            " ORDER BY start_time",
            (tz_name, tz_name, since),
        ).fetchall()
    return aggregate_daily_rides([dict(r) for r in rows], days=days)


@router.get("/summary/weekly", response_model=list[WeeklySummary])
def weekly_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    from datetime import date as dt_date
    tz_name = str(tz)
    query = (
        "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date,"
        " duration_s, tss, distance_m, total_ascent, avg_power, avg_hr, best_20min_power"
        " FROM rides WHERE start_time IS NOT NULL"
    )
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE"
        params.extend([tz_name, end_date])
    query += " ORDER BY start_time"

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
    tz: ZoneInfo = Depends(get_client_tz),
):
    tz_name = str(tz)
    query = """
        SELECT
            TO_CHAR((start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE, 'YYYY-MM') as month,
            COUNT(*) as rides,
            ROUND(CAST(SUM(duration_s) / 3600.0 AS NUMERIC), 1) as duration_h,
            ROUND(CAST(SUM(COALESCE(tss, 0)) AS NUMERIC), 1) as tss,
            ROUND(CAST(SUM(COALESCE(distance_m, 0)) / 1000.0 AS NUMERIC), 1) as distance_km,
            CAST(SUM(COALESCE(total_ascent, 0)) AS INTEGER) as ascent_m,
            ROUND(CAST(AVG(CASE WHEN avg_power > 0 THEN avg_power END) AS NUMERIC), 0) as avg_power,
            ROUND(CAST(AVG(CASE WHEN avg_hr > 0 THEN avg_hr END) AS NUMERIC), 0) as avg_hr,
            MAX(best_20min_power) as best_20min
        FROM rides
        WHERE start_time IS NOT NULL
    """
    params: list = [tz_name]
    if start_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
        params.extend([tz_name, start_date])
    if end_date:
        query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE"
        params.extend([tz_name, end_date])
    query += " GROUP BY month ORDER BY month"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [MonthlySummary(**dict(r)) for r in rows]


@router.get("/{ride_id}", response_model=RideDetail)
def get_ride(ride_id: int, user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    tz_name = str(tz)
    with get_db() as conn:
        ride = conn.execute(
            "SELECT *, (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date FROM rides WHERE id = ?",
            (tz_name, ride_id),
        ).fetchone()
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
def delete_ride(ride_id: int, user: CurrentUser = Depends(require_write), tz: ZoneInfo = Depends(get_client_tz)):
    tz_name = str(tz)
    with get_db() as conn:
        # 1. Get ride local date for PMC recalculation (derived from start_time)
        ride = conn.execute(
            "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS local_date"
            " FROM rides WHERE id = ?",
            (tz_name, ride_id),
        ).fetchone()
        if not ride:
            raise HTTPException(status_code=404, detail="Ride not found")

        ride_date = ride["local_date"]

        # 2. Delete dependencies
        conn.execute("DELETE FROM ride_records WHERE ride_id = ?", (ride_id,))
        conn.execute("DELETE FROM ride_laps WHERE ride_id = ?", (ride_id,))
        conn.execute("DELETE FROM power_bests WHERE ride_id = ?", (ride_id,))

        # 3. Delete ride
        conn.execute("DELETE FROM rides WHERE id = ?", (ride_id,))

        # 4. Recalculate PMC
        compute_daily_pmc(conn, since_date=ride_date)

    return {"status": "ok"}
