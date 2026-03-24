"""Training plan endpoints."""

import xml.etree.ElementTree as ET
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel

from server.database import get_db
from server.models.schemas import PlannedWorkout, PeriodizationPhase
from server.services.workout_generator import generate_zwo, WORKOUT_TEMPLATES

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


@router.get("/workout-types")
def list_workout_types():
    """List available workout templates."""
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in WORKOUT_TEMPLATES.items()
    ]


class GenerateWorkoutRequest(BaseModel):
    workout_type: str
    duration_minutes: int = 60
    ftp: int = 261


@router.post("/workouts/generate")
def generate_workout(req: GenerateWorkoutRequest):
    """Generate a ZWO workout file."""
    try:
        xml_str, name = generate_zwo(req.workout_type, req.duration_minutes, req.ftp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"name": name, "xml": xml_str}


@router.post("/workouts/generate/download")
def download_workout(req: GenerateWorkoutRequest):
    """Generate and download a ZWO workout file."""
    try:
        xml_str, name = generate_zwo(req.workout_type, req.duration_minutes, req.ftp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    filename = name.lower().replace(" ", "_") + ".zwo"
    return Response(
        content=xml_str,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_zwo_steps(xml_str: str, ftp: int = 261) -> list[dict]:
    """Parse ZWO XML into a list of workout steps with absolute watts."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    workout_el = root.find("workout")
    if workout_el is None:
        return []

    steps = []
    elapsed = 0

    for el in workout_el:
        tag = el.tag

        if tag == "IntervalsT":
            repeat = int(el.get("Repeat", "1"))
            on_dur = int(float(el.get("OnDuration", "0")))
            off_dur = int(float(el.get("OffDuration", "0")))
            on_pct = float(el.get("OnPower", "1.0"))
            off_pct = float(el.get("OffPower", "0.5"))
            for i in range(repeat):
                steps.append({
                    "type": "Interval",
                    "label": f"Interval {i+1}/{repeat}",
                    "duration_s": on_dur,
                    "start_s": elapsed,
                    "power_pct": on_pct,
                    "power_watts": round(on_pct * ftp),
                })
                elapsed += on_dur
                steps.append({
                    "type": "Recovery",
                    "label": "Recovery",
                    "duration_s": off_dur,
                    "start_s": elapsed,
                    "power_pct": off_pct,
                    "power_watts": round(off_pct * ftp),
                })
                elapsed += off_dur

        elif tag in ("Warmup", "Cooldown"):
            dur = int(float(el.get("Duration", "0")))
            low_pct = float(el.get("PowerLow", "0.4"))
            high_pct = float(el.get("PowerHigh", "0.65"))
            avg_pct = (low_pct + high_pct) / 2
            steps.append({
                "type": tag,
                "label": tag,
                "duration_s": dur,
                "start_s": elapsed,
                "power_pct": avg_pct,
                "power_low_pct": low_pct,
                "power_high_pct": high_pct,
                "power_watts": round(avg_pct * ftp),
                "power_low_watts": round(low_pct * ftp),
                "power_high_watts": round(high_pct * ftp),
            })
            elapsed += dur

        elif tag == "SteadyState":
            dur = int(float(el.get("Duration", "0")))
            pct = float(el.get("Power", "0.65"))
            steps.append({
                "type": "SteadyState",
                "label": _zone_label(pct),
                "duration_s": dur,
                "start_s": elapsed,
                "power_pct": pct,
                "power_watts": round(pct * ftp),
            })
            elapsed += dur

    return steps


def _zone_label(pct: float) -> str:
    """Return a human-readable zone label for a given FTP percentage."""
    if pct < 0.56:
        return "Z1 Recovery"
    elif pct < 0.76:
        return "Z2 Endurance"
    elif pct < 0.91:
        return "Z3 Tempo / Sweet Spot"
    elif pct < 1.06:
        return "Z4 Threshold"
    elif pct < 1.21:
        return "Z5 VO2max"
    else:
        return "Z6 Anaerobic"


@router.get("/workouts/{workout_id}")
def get_workout_detail(workout_id: int):
    """Get parsed workout detail with steps for visualization."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM planned_workouts WHERE id = ?", (workout_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workout not found")

    workout = dict(row)

    # Get FTP for absolute watts
    with get_db() as conn:
        ftp_row = conn.execute(
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
        ).fetchone()
    ftp = ftp_row["ftp"] if ftp_row else 261

    steps = []
    if workout.get("workout_xml"):
        steps = _parse_zwo_steps(workout["workout_xml"], ftp)

    total_duration = sum(s["duration_s"] for s in steps) if steps else workout.get("total_duration_s", 0)

    return {
        "id": workout["id"],
        "date": workout["date"],
        "name": workout["name"],
        "sport": workout["sport"],
        "total_duration_s": total_duration,
        "ftp": ftp,
        "steps": steps,
        "has_xml": bool(workout.get("workout_xml")),
    }


@router.get("/workouts/{workout_id}/download")
def download_planned_workout(workout_id: int, fmt: str = "fit"):
    """Download a planned workout file.

    Args:
        workout_id: The workout ID.
        fmt: Format - 'fit' (Garmin) or 'zwo' (Zwift/TrainingPeaks).
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT name, workout_xml FROM planned_workouts WHERE id = ?", (workout_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workout not found")
    if not row["workout_xml"]:
        raise HTTPException(status_code=404, detail="No workout file available")

    # Get FTP for FIT export
    with get_db() as conn:
        ftp_row = conn.execute(
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1"
        ).fetchone()
    ftp = ftp_row["ftp"] if ftp_row else 261

    safe_name = (row["name"] or "workout").lower().replace(" ", "_").replace("/", "_")

    if fmt == "zwo":
        return Response(
            content=row["workout_xml"],
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.zwo"'},
        )
    else:
        from server.services.fit_export import zwo_to_fit
        fit_bytes = zwo_to_fit(row["workout_xml"], ftp=ftp, workout_name=row["name"] or "Workout")
        return Response(
            content=fit_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.fit"'},
        )
