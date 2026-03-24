"""Training plan endpoints."""

from fastapi import APIRouter, Query
from typing import Optional

from server.database import get_db
from server.models.schemas import PlannedWorkout, PeriodizationPhase

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.get("/macro", response_model=list[PeriodizationPhase])
def get_macro_plan():
    """Get periodization phases."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM periodization_phases ORDER BY start_date").fetchall()
    return [PeriodizationPhase(**dict(r)) for r in rows]


@router.get("/week/{date}")
def get_week_plan(date: str):
    """Get planned workouts for the week containing the given date."""
    from datetime import datetime, timedelta
    dt = datetime.fromisoformat(date)
    # Start of week (Monday)
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    with get_db() as conn:
        planned = conn.execute(
            "SELECT * FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (start_str, end_str),
        ).fetchall()

        actual = conn.execute(
            "SELECT id, date, sport, sub_sport, duration_s, tss, avg_power, normalized_power, avg_hr, distance_m, total_ascent FROM rides WHERE date >= ? AND date <= ? ORDER BY date",
            (start_str, end_str),
        ).fetchall()

    return {
        "week_start": start_str,
        "week_end": end_str,
        "planned": [dict(p) for p in planned],
        "actual": [dict(a) for a in actual],
    }


@router.get("/compliance")
def plan_compliance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Planned vs actual workout compliance."""
    with get_db() as conn:
        pw_query = "SELECT date FROM planned_workouts WHERE 1=1"
        r_query = "SELECT DISTINCT date FROM rides WHERE 1=1"
        params = []
        if start_date:
            pw_query += " AND date >= ?"
            r_query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            pw_query += " AND date <= ?"
            r_query += " AND date <= ?"
            params.append(end_date)

        planned_dates = set(r["date"] for r in conn.execute(pw_query, params).fetchall() if r["date"])
        actual_dates = set(r["date"] for r in conn.execute(r_query, params).fetchall())

    completed = planned_dates & actual_dates
    missed = planned_dates - actual_dates
    extra = actual_dates - planned_dates

    total_planned = len(planned_dates)
    return {
        "planned": total_planned,
        "completed": len(completed),
        "missed": len(missed),
        "extra": len(extra),
        "compliance_pct": round(100 * len(completed) / total_planned, 1) if total_planned > 0 else 0,
    }
