"""Training plan endpoints."""

import xml.etree.ElementTree as ET
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel

from zoneinfo import ZoneInfo

from server.auth import CurrentUser, require_read, require_write
from server.database import get_db, get_athlete_setting
from server.dependencies import get_client_tz
from server.models.schemas import PlannedWorkout, PeriodizationPhase
from server.queries import get_current_ftp as _get_current_ftp_with_conn, get_periodization_phases, get_week_planned_and_actual
from server.services.workout_generator import generate_zwo, list_templates, get_template
from server.logging_config import get_logger
from server.zones import power_zone_label

logger = get_logger(__name__)


def _get_current_ftp() -> int:
    """Get current FTP (convenience wrapper that manages its own connection)."""
    with get_db() as conn:
        return _get_current_ftp_with_conn(conn)

router = APIRouter(prefix="/api/plan", tags=["plan"])


@router.get("/activity-dates")
def get_activity_dates(user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    """Return sorted list of all dates that have a ride or planned workout."""
    tz_name = str(tz)
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date FROM ("
                "  SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date"
                "   FROM rides WHERE start_time IS NOT NULL"
                "  UNION"
                "  SELECT date::TEXT AS date FROM planned_workouts WHERE date IS NOT NULL"
                ") AS combined ORDER BY date",
                (tz_name,),
            ).fetchall()
        return [r["date"] for r in rows]
    except Exception as e:
        logger.error("activity_dates_failed", error=str(e), exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch activity dates: {str(e)}")


@router.get("/macro", response_model=list[PeriodizationPhase])
def get_macro_plan(user: CurrentUser = Depends(require_read)):
    """Get periodization phases."""
    with get_db() as conn:
        rows = get_periodization_phases(conn)
    return [PeriodizationPhase(**r) for r in rows]


@router.get("/week/{date}")
def get_week_plan(date: str, user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    """Get planned workouts for the week containing the given date."""
    from datetime import datetime, timedelta
    dt = datetime.fromisoformat(date)
    # Start of week (Monday)
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    with get_db() as conn:
        planned, actual = get_week_planned_and_actual(conn, start_str, end_str, tz_name=str(tz))

    return {
        "week_start": start_str,
        "week_end": end_str,
        "planned": planned,
        "actual": actual,
    }


@router.post("/week/batch")
def get_week_plans_batch(dates: list[str], user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    """Get planned workouts for multiple weeks in a single request."""
    from datetime import datetime, timedelta

    if not dates or len(dates) > 10:
        raise HTTPException(status_code=400, detail="Provide 1-10 dates")

    results = []
    with get_db() as conn:
        for date in dates:
            dt = datetime.fromisoformat(date)
            start = dt - timedelta(days=dt.weekday())
            end = start + timedelta(days=6)
            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d")
            planned, actual = get_week_planned_and_actual(conn, start_str, end_str, tz_name=str(tz))
            results.append({
                "week_start": start_str,
                "week_end": end_str,
                "planned": planned,
                "actual": actual,
            })
    return results


@router.get("/weekly-overview")
def weekly_overview(user: CurrentUser = Depends(require_read), tz: ZoneInfo = Depends(get_client_tz)):
    """Weekly rollup of planned vs actual hours and TSS across the full plan.

    Returns one entry per week for every week spanned by periodization phases,
    with phase targets, planned workout totals, and actual ride totals.
    """
    from datetime import date as dt_date, timedelta
    from collections import defaultdict

    with get_db() as conn:
        phases = get_periodization_phases(conn)
        if not phases:
            return []

        plan_start = dt_date.fromisoformat(str(phases[0]["start_date"]))
        plan_end = dt_date.fromisoformat(str(phases[-1]["end_date"]))

        # Monday of the first week
        first_monday = plan_start - timedelta(days=plan_start.weekday())
        # Sunday of the last week
        last_sunday = plan_end + timedelta(days=(6 - plan_end.weekday()))

        # Build phase lookup
        phase_list = phases

        def phase_for_monday(mon: dt_date):
            mid = mon + timedelta(days=3)  # use mid-week to assign phase
            mid_str = mid.isoformat()
            for p in phase_list:
                if str(p["start_date"]) <= mid_str <= str(p["end_date"]):
                    return p
            return None

        # Planned workouts aggregated by week
        planned_rows = conn.execute(
            "SELECT date, total_duration_s, planned_tss FROM planned_workouts WHERE date >= ? AND date <= ? ORDER BY date",
            (first_monday.isoformat(), last_sunday.isoformat()),
        ).fetchall()

        planned_by_week = defaultdict(lambda: {"hours": 0.0, "tss": 0.0, "workouts": 0})
        for r in planned_rows:
            d = dt_date.fromisoformat(str(r["date"]))
            mon = d - timedelta(days=d.weekday())
            pw = planned_by_week[mon.isoformat()]
            pw["workouts"] += 1
            pw["hours"] += (r["total_duration_s"] or 0) / 3600
            pw["tss"] += float(r["planned_tss"] or 0)

        # Actual rides aggregated by week
        tz_name = str(tz)
        actual_rows = conn.execute(
            "SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date,"
            " duration_s, tss FROM rides"
            " WHERE (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
            " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE"
            " ORDER BY start_time",
            (tz_name, tz_name, first_monday.isoformat(), tz_name, last_sunday.isoformat()),
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
    tz: ZoneInfo = Depends(get_client_tz),
):
    """Planned vs actual workout compliance."""
    tz_name = str(tz)
    with get_db() as conn:
        pw_query = "SELECT date FROM planned_workouts WHERE 1=1"
        pw_params: list = []
        r_query = (
            "SELECT DISTINCT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date"
            " FROM rides WHERE 1=1"
        )
        r_params: list = [tz_name]
        if start_date:
            pw_query += " AND date >= ?"
            pw_params.append(start_date)
            r_query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE"
            r_params.extend([tz_name, start_date])
        if end_date:
            pw_query += " AND date <= ?"
            pw_params.append(end_date)
            r_query += " AND (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE <= ?::DATE"
            r_params.extend([tz_name, end_date])

        # Use str() on planned_workouts.date (now DATE type returning datetime.date)
        # to match the string format from actual rides (::TEXT cast).
        planned_dates = set(str(r["date"]) for r in conn.execute(pw_query, pw_params).fetchall() if r["date"])
        actual_dates = set(r["date"] for r in conn.execute(r_query, r_params).fetchall())

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
    ftp = _get_current_ftp()

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
    ftp: int = 0


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
    from server.services.intervals_icu import push_workout, is_configured, find_matching_workout

    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail="intervals.icu not configured. Set INTERVALS_ICU_API_KEY and INTERVALS_ICU_ATHLETE_ID environment variables.",
        )

    from server.services.intervals_icu import compute_sync_hash
    from datetime import datetime, timezone

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, date, workout_xml, total_duration_s, icu_event_id FROM planned_workouts WHERE id = ?",
            (workout_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")
        if not row["workout_xml"]:
            raise HTTPException(status_code=400, detail="No workout file available")

        w_name = row["name"] or "Workout"
        moving_time = int(row["total_duration_s"] or 0)
        icu_event_id = row.get("icu_event_id")

        # Step 2.B Implementation: Check for existing event on Intervals.icu if we don't have an ID
        w_date = str(row["date"])
        if not icu_event_id:
            icu_event_id = find_matching_workout(w_date, w_name)

        result = push_workout(
            date=w_date,
            name=w_name,
            zwo_xml=row["workout_xml"],
            moving_time_secs=moving_time,
            icu_event_id=icu_event_id,
        )

        if result.get("error") or result.get("status") == "error":
            raise HTTPException(status_code=502, detail=result.get("error") or result.get("message", "Sync failed"))

        # Store event_id and hash
        current_hash = compute_sync_hash(w_name, w_date, row["workout_xml"], moving_time)
        conn.execute(
            "UPDATE planned_workouts SET icu_event_id = ?, sync_hash = ?, synced_at = ? WHERE id = ?",
            (result.get("event_id"), current_hash, datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]),
        )

    return result


@router.get("/integrations/status")
def integration_status(user: CurrentUser = Depends(require_read)):
    """Check if external integrations are configured."""
    from server.services.intervals_icu import is_configured
    return {"intervals_icu": is_configured()}


def _parse_zwo_steps(xml_str: str, ftp: int = 0) -> list[dict]:
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

        if tag in ("IntervalsT", "Intervals"):
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

        elif tag in ("SteadyState", "Ramp", "FreeRide"):
            dur = int(float(el.get("Duration", "0")))
            if tag == "FreeRide":
                 pct = 0.60 # Default for display
            else:
                 pct = float(el.get("Power", el.get("PowerHigh", "0.65")))
            
            steps.append({
                "type": tag,
                "label": power_zone_label(pct) if tag != "FreeRide" else "Free Ride",
                "duration_s": dur,
                "start_s": elapsed,
                "power_pct": pct,
                "power_watts": round(pct * ftp),
            })
            elapsed += dur

    return steps



@router.delete("/workouts/{workout_id}")
def delete_workout(workout_id: int, user: CurrentUser = Depends(require_write)):
    """Delete a planned workout."""
    with get_db() as conn:
        row = conn.execute("SELECT id, icu_event_id FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workout not found")
        icu_event_id = row.get("icu_event_id")
        conn.execute("DELETE FROM planned_workouts WHERE id = ?", (workout_id,))
    # Clean up stale event on intervals.icu
    if icu_event_id:
        try:
            from server.services.intervals_icu import delete_event
            delete_event(icu_event_id)
        except Exception:
            pass
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

    ftp = _get_current_ftp()

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
    ftp = _get_current_ftp()

    steps = []
    if workout.get("workout_xml"):
        steps = _parse_zwo_steps(workout["workout_xml"], ftp)

    total_duration = sum(s["duration_s"] for s in steps) if steps else workout.get("total_duration_s", 0)

    return {
        "id": workout["id"],
        "date": str(workout["date"]),
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
            "SELECT ftp FROM rides WHERE ftp > 0 ORDER BY start_time DESC LIMIT 1"
        ).fetchone()
    ftp = ftp_row["ftp"] if ftp_row else 0

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
            scheduled_date=str(row["date"]),
        )
        return Response(
            content=tcx_str,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.tcx"'},
        )
