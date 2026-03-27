"""Training plan endpoints."""

import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel

from server.auth import CurrentUser, require_read, require_write
from server.database import get_db
from server.models.schemas import PlannedWorkout, PeriodizationPhase
from server.services.workout_generator import generate_zwo, list_templates, get_template

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.get("/activity-dates")
def get_activity_dates(user: CurrentUser = Depends(require_read)):
    """Return sorted list of all dates that have a ride or planned workout."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM ("
            "  SELECT SUBSTR(date, 1, 10) AS date FROM rides"
            "  UNION"
            "  SELECT SUBSTR(date, 1, 10) AS date FROM planned_workouts"
            ") ORDER BY date"
        ).fetchall()
    return [r["date"] for r in rows]


@router.get("/macro", response_model=list[PeriodizationPhase])
def get_macro_plan(user: CurrentUser = Depends(require_read)):
    """Get periodization phases."""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM periodization_phases ORDER BY start_date").fetchall()
    return [PeriodizationPhase(**dict(r)) for r in rows]


@router.get("/week/{date}")
def get_week_plan(date: str, user: CurrentUser = Depends(require_read)):
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


@router.get("/weekly-overview")
def weekly_overview(user: CurrentUser = Depends(require_read)):
    """Weekly rollup of planned vs actual hours and TSS across the full plan.

    Returns one entry per week for every week spanned by periodization phases,
    with phase targets, planned workout totals, and actual ride totals.
    """
    from datetime import date as dt_date, timedelta
    from collections import defaultdict

    with get_db() as conn:
        phases = conn.execute(
            "SELECT * FROM periodization_phases ORDER BY start_date"
        ).fetchall()
        if not phases:
            return []

        plan_start = dt_date.fromisoformat(phases[0]["start_date"])
        plan_end = dt_date.fromisoformat(phases[-1]["end_date"])

        # Monday of the first week
        first_monday = plan_start - timedelta(days=plan_start.weekday())
        # Sunday of the last week
        last_sunday = plan_end + timedelta(days=(6 - plan_end.weekday()))

        # Build phase lookup
        phase_list = [dict(p) for p in phases]

        def phase_for_monday(mon: dt_date):
            mid = mon + timedelta(days=3)  # use mid-week to assign phase
            mid_str = mid.isoformat()
            for p in phase_list:
                if p["start_date"] <= mid_str <= p["end_date"]:
                    return p
            return None

        # Planned workouts aggregated by week
        planned_rows = conn.execute(
            "SELECT date, total_duration_s, planned_tss FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (first_monday.isoformat(), last_sunday.isoformat()),
        ).fetchall()

        planned_by_week = defaultdict(lambda: {"hours": 0.0, "tss": 0.0, "workouts": 0})
        for r in planned_rows:
            d = dt_date.fromisoformat(r["date"])
            mon = d - timedelta(days=d.weekday())
            pw = planned_by_week[mon.isoformat()]
            pw["workouts"] += 1
            pw["hours"] += (r["total_duration_s"] or 0) / 3600
            pw["tss"] += float(r["planned_tss"] or 0)

        # Actual rides aggregated by week
        actual_rows = conn.execute(
            "SELECT date, duration_s, tss FROM rides WHERE date >= ? AND date <= ? ORDER BY date",
            (first_monday.isoformat(), last_sunday.isoformat()),
        ).fetchall()

        actual_by_week = defaultdict(lambda: {"hours": 0.0, "tss": 0.0, "rides": 0})
        for r in actual_rows:
            d = dt_date.fromisoformat(r["date"])
            mon = d - timedelta(days=d.weekday())
            aw = actual_by_week[mon.isoformat()]
            aw["rides"] += 1
            aw["hours"] += (r["duration_s"] or 0) / 3600
            aw["tss"] += float(r["tss"] or 0)

        # Build week-by-week output
        result = []
        mon = first_monday
        while mon <= last_sunday:
            mon_str = mon.isoformat()
            phase = phase_for_monday(mon)
            pw = planned_by_week.get(mon_str, {"hours": 0, "tss": 0, "workouts": 0})
            aw = actual_by_week.get(mon_str, {"hours": 0, "tss": 0, "rides": 0})
            result.append({
                "week_start": mon_str,
                "phase": phase["name"] if phase else None,
                "target_hours_low": phase["hours_per_week_low"] if phase else None,
                "target_hours_high": phase["hours_per_week_high"] if phase else None,
                "target_tss_low": phase["tss_target_low"] if phase else None,
                "target_tss_high": phase["tss_target_high"] if phase else None,
                "planned_hours": round(pw["hours"], 1),
                "planned_tss": round(pw["tss"]),
                "planned_workouts": pw["workouts"],
                "actual_hours": round(aw["hours"], 1),
                "actual_tss": round(aw["tss"]),
                "actual_rides": aw["rides"],
            })
            mon += timedelta(days=7)

    return result


@router.get("/compliance")
def plan_compliance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_read),
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
def list_workout_types(user: CurrentUser = Depends(require_read)):
    """List available workout templates."""
    return [
        {"key": t["key"], "name": t["name"], "description": t["description"]}
        for t in list_templates()
    ]


@router.get("/templates")
def get_templates(category: Optional[str] = Query(None), user: CurrentUser = Depends(require_read)):
    """List all workout templates with full details."""
    templates = list_templates()
    if category:
        templates = [t for t in templates if t["category"] == category]
    return [
        {
            "id": t["id"],
            "key": t["key"],
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
            "source": t["source"],
            "created_at": t["created_at"],
            "steps": t["steps"],
        }
        for t in templates
    ]


@router.get("/templates/{template_id}")
def get_template_detail(template_id: int, user: CurrentUser = Depends(require_read)):
    """Get a single workout template with parsed steps in viewer-compatible format."""
    from server.database import get_db
    import json
    with get_db() as conn:
        row = conn.execute("SELECT * FROM workout_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    t = dict(row)
    raw_steps = json.loads(t["steps"])

    # Get FTP for absolute watts
    with get_db() as conn:
        ftp_row = conn.execute("SELECT ftp FROM rides WHERE ftp > 0 ORDER BY date DESC LIMIT 1").fetchone()
    ftp = ftp_row["ftp"] if ftp_row else 261

    # Generate ZWO XML from template, then parse into viewer-compatible steps
    xml_str, _ = generate_zwo(t["key"], duration_minutes=60, ftp=ftp)
    steps = _parse_zwo_steps(xml_str, ftp)
    total_s = sum(s["duration_s"] for s in steps)

    return {
        "id": t["id"],
        "key": t["key"],
        "name": t["name"],
        "description": t["description"],
        "category": t["category"],
        "source": t["source"],
        "ftp": ftp,
        "total_duration_s": total_s,
        "steps": steps,
        "has_xml": True,
    }


class GenerateWorkoutRequest(BaseModel):
    workout_type: str
    duration_minutes: int = 60
    ftp: int = 261


@router.post("/workouts/generate")
def generate_workout(req: GenerateWorkoutRequest, user: CurrentUser = Depends(require_write)):
    """Generate a ZWO workout file."""
    try:
        xml_str, name = generate_zwo(req.workout_type, req.duration_minutes, req.ftp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"name": name, "xml": xml_str}


@router.post("/workouts/generate/download")
def download_workout(req: GenerateWorkoutRequest, user: CurrentUser = Depends(require_write)):
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


@router.post("/workouts/{workout_id}/sync")
def sync_workout_to_intervals(workout_id: int, user: CurrentUser = Depends(require_write)):
    """Push a planned workout to intervals.icu for Garmin sync."""
    from server.services.intervals_icu import push_workout, is_configured

    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail="intervals.icu not configured. Set INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID environment variables.",
        )

    with get_db() as conn:
        row = conn.execute(
            "SELECT name, date, workout_xml, total_duration_s FROM planned_workouts WHERE id = ?",
            (workout_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workout not found")
    if not row["workout_xml"]:
        raise HTTPException(status_code=400, detail="No workout file available")

    result = push_workout(
        date=row["date"],
        name=row["name"] or "Workout",
        zwo_xml=row["workout_xml"],
        moving_time_secs=int(row["total_duration_s"] or 0),
    )

    if result.get("error") or result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("error") or result.get("message", "Sync failed"))

    return result


@router.get("/integrations/status")
def integration_status(user: CurrentUser = Depends(require_read)):
    """Check if external integrations are configured."""
    from server.services.intervals_icu import is_configured
    return {"intervals_icu": is_configured()}


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


@router.delete("/workouts/{workout_id}")
def delete_workout(workout_id: int, user: CurrentUser = Depends(require_write)):
    """Delete a planned workout."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")
        conn.execute("DELETE FROM planned_workouts WHERE id = ?", (workout_id,))
    return {"status": "ok"}


@router.get("/workouts/by-date/{date}")
def get_workout_by_date(date: str, user: CurrentUser = Depends(require_read)):
    """Get parsed workout steps for a given date (for ride overlay)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM planned_workouts WHERE date = ? LIMIT 1", (date,)
        ).fetchone()

    if not row:
        return None

    workout = dict(row)

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
        "name": workout["name"],
        "total_duration_s": total_duration,
        "planned_tss": workout.get("planned_tss"),
        "ftp": ftp,
        "steps": steps,
        "coach_notes": workout.get("coach_notes"),
        "athlete_notes": workout.get("athlete_notes"),
    }


@router.get("/workouts/{workout_id}")
def get_workout_detail(workout_id: int, user: CurrentUser = Depends(require_read)):
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
        "coach_notes": workout.get("coach_notes"),
        "athlete_notes": workout.get("athlete_notes"),
    }


class WorkoutNotesUpdate(BaseModel):
    athlete_notes: Optional[str] = None


@router.put("/workouts/{workout_id}/notes")
def update_workout_notes(workout_id: int, body: WorkoutNotesUpdate, user: CurrentUser = Depends(require_write)):
    """Update athlete's pre-ride notes on a planned workout."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")
        conn.execute(
            "UPDATE planned_workouts SET athlete_notes = ? WHERE id = ?",
            (body.athlete_notes, workout_id),
        )
    return {"status": "ok"}


@router.get("/workouts/{workout_id}/download")
def download_planned_workout(workout_id: int, fmt: str = "tcx", user: CurrentUser = Depends(require_read)):
    """Download a planned workout file.

    Args:
        workout_id: The workout ID.
        fmt: Format - 'tcx' (Garmin), 'fit' (Garmin device), or 'zwo' (Zwift/TrainingPeaks).
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT name, date, workout_xml FROM planned_workouts WHERE id = ?", (workout_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workout not found")
    if not row["workout_xml"]:
        raise HTTPException(status_code=404, detail="No workout file available")

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
    elif fmt == "fit":
        from server.services.fit_export import zwo_to_fit
        fit_bytes = zwo_to_fit(row["workout_xml"], ftp=ftp, workout_name=row["name"] or "Workout")
        return Response(
            content=fit_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.fit"'},
        )
    else:  # tcx (default)
        from server.services.tcx_export import zwo_to_tcx
        tcx_str = zwo_to_tcx(
            row["workout_xml"],
            ftp=ftp,
            workout_name=row["name"] or "Workout",
            scheduled_date=row["date"],
        )
        return Response(
            content=tcx_str,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.tcx"'},
        )
