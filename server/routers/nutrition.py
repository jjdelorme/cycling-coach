"""Nutrition meal logging and Nutritionist chat endpoints."""

import uuid
import base64
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import Response

from server.auth import CurrentUser, require_read, require_write
from server.dependencies import get_client_tz
from server.models.schemas import (
    MealSummary, MealDetail, MealItem, MacroTargets,
    DailyNutritionSummary, MealUpdateRequest,
    NutritionChatRequest, NutritionChatResponse,
    SessionSummary, SessionDetail, SessionMessage,
    PlannedMeal, MealPlanDay, MealPlanDayTotals,
    DietaryPreferencesUpdate,
)
from server.database import get_db
from server.queries import (
    get_meals_for_date, get_meal_items, get_macro_targets,
    get_daily_meal_totals, get_planned_meals_for_range,
    get_planned_meals_for_date,
)
from server.nutrition.photo import upload_meal_photo, download_photo

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

DAILY_ANALYSIS_LIMIT = 20


def _photo_url(meal_id: int | None, has_photo: bool) -> str:
    """Build the proxy photo URL for a meal, or empty string if no photo."""
    if not has_photo or meal_id is None:
        return ""
    return f"/api/nutrition/photos/{meal_id}"


# ---------------------------------------------------------------------------
# Meal photos (proxy)
# ---------------------------------------------------------------------------

@router.get("/photos/{meal_id}")
async def get_photo(meal_id: int):
    """Serve a meal photo from GCS via the API.

    No auth required — <img> tags can't send Authorization headers,
    and meal photos are non-sensitive data.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT photo_gcs_path FROM meal_logs WHERE id = %s",
            (meal_id,),
        ).fetchone()

    if not row or not row["photo_gcs_path"]:
        raise HTTPException(404, "No photo for this meal")

    data = download_photo(row["photo_gcs_path"])
    if data is None:
        raise HTTPException(404, "Photo not found in storage")

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# Meal CRUD
# ---------------------------------------------------------------------------

ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/mp4", "audio/mpeg"}


@router.post("/meals", status_code=201)
async def create_meal(
    file: UploadFile = File(...),
    audio: UploadFile | None = File(None),
    comment: str = Form(""),
    meal_type: str = Form(""),
    user: CurrentUser = Depends(require_write),
):
    """Analyze and log a meal photo. Rate-limited to 20 analyses/day."""
    from datetime import datetime, timezone
    from server.nutrition.agent import chat as nutrition_chat

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Rate limit check — uses existing idx_meal_logs_date index
    with get_db() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
            (today, "athlete"),
        ).fetchone()
        if count_row and count_row["cnt"] >= DAILY_ANALYSIS_LIMIT:
            raise HTTPException(
                429,
                f"Daily meal analysis limit reached ({DAILY_ANALYSIS_LIMIT}/day). "
                "You can still edit existing meals or chat with the nutritionist.",
            )

    # Validate file
    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 10MB)")

    # Upload to GCS and get resized bytes for agent
    gcs_path, resized_bytes = upload_meal_photo(image_bytes, file.content_type)

    # Read audio bytes if provided
    audio_bytes = None
    audio_mime = None
    if audio and audio.content_type in ALLOWED_AUDIO_TYPES:
        audio_bytes = await audio.read()
        audio_mime = audio.content_type
        if len(audio_bytes) > 5 * 1024 * 1024:  # 5MB max for voice notes
            raise HTTPException(400, "Audio too large (max 5MB)")

    # Build prompt
    prompt = comment or "Analyze this meal and estimate its macros."
    if meal_type:
        prompt += f" This is a {meal_type} meal."
    if audio_bytes:
        prompt += " I've also included a voice note describing the meal."

    session_id = str(uuid.uuid4())
    try:
        response_text, _, _ = await nutrition_chat(
            message=prompt,
            user_id=user.email if hasattr(user, "email") else "athlete",
            session_id=session_id,
            user=user,
            image_data=resized_bytes,
            image_mime_type="image/jpeg",
            photo_gcs_path=gcs_path,
            audio_data=audio_bytes,
            audio_mime_type=audio_mime,
        )
    except Exception as e:
        from server.logging_config import get_logger as _gl
        _gl(__name__).error("nutrition_agent_error", exc_info=e, error_type=type(e).__name__, error_str=str(e))
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            raise HTTPException(429, "The AI model is currently busy. Please try again in a moment.")
        raise

    # The agent should have called save_meal_analysis tool.
    # Fetch the most recent meal to return it.
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM meal_logs WHERE photo_gcs_path = %s ORDER BY id DESC LIMIT 1",
            (gcs_path,),
        ).fetchone()

        if not row:
            # Agent didn't save -- return the response text as a fallback
            return {"status": "analysis_only", "response": response_text}

        meal = dict(row)
        items = get_meal_items(conn, meal["id"])

    meal["photo_url"] = _photo_url(meal["id"], bool(meal.get("photo_gcs_path")))
    meal["items"] = items

    return meal


@router.get("/meals")
async def list_meals(
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(require_read),
):
    """List meals with optional date range filter."""
    with get_db() as conn:
        query = "SELECT * FROM meal_logs WHERE user_id = %s"
        params: list = ["athlete"]

        if start_date:
            query += " AND date >= %s"
            params.append(start_date)
        if end_date:
            query += " AND date <= %s"
            params.append(end_date)

        # Get total count
        count_row = conn.execute(
            query.replace("SELECT *", "SELECT COUNT(*) AS total"), params
        ).fetchone()
        total = count_row["total"] if count_row else 0

        query += " ORDER BY date DESC, logged_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

    meals = []
    for r in rows:
        m = dict(r)
        m["photo_url"] = _photo_url(m["id"], bool(m.get("photo_gcs_path")))
        meals.append(m)

    return {"meals": meals, "total": total, "limit": limit, "offset": offset}


@router.get("/meals/{meal_id}")
async def get_meal(meal_id: int, user: CurrentUser = Depends(require_read)):
    """Get a single meal with its itemized breakdown."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")
        items = get_meal_items(conn, meal_id)

    meal = dict(row)
    meal["photo_url"] = _photo_url(meal["id"], bool(meal.get("photo_gcs_path")))
    meal["items"] = items
    return meal


@router.put("/meals/{meal_id}")
async def update_meal_endpoint(
    meal_id: int,
    req: MealUpdateRequest,
    user: CurrentUser = Depends(require_write),
):
    """Update a meal's macro values (user edits after AI analysis)."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")

        updates = []
        params = []
        if req.total_calories is not None:
            updates.append("total_calories = %s")
            params.append(req.total_calories)
        if req.total_protein_g is not None:
            updates.append("total_protein_g = %s")
            params.append(req.total_protein_g)
        if req.total_carbs_g is not None:
            updates.append("total_carbs_g = %s")
            params.append(req.total_carbs_g)
        if req.total_fat_g is not None:
            updates.append("total_fat_g = %s")
            params.append(req.total_fat_g)
        if req.meal_type is not None:
            updates.append("meal_type = %s")
            params.append(req.meal_type)
        if req.date is not None:
            updates.append("date = %s")
            params.append(req.date)
        if req.logged_at is not None:
            updates.append("logged_at = %s")
            params.append(req.logged_at)

        has_macro_changes = len(updates) > 0

        if req.user_notes is not None:
            updates.append("user_notes = %s")
            params.append(req.user_notes)

        if updates:
            if has_macro_changes:
                updates.append("edited_by_user = TRUE")
            params.append(meal_id)
            conn.execute(f"UPDATE meal_logs SET {', '.join(updates)} WHERE id = %s", params)

        # Replace items if provided
        if req.items is not None:
            conn.execute("DELETE FROM meal_items WHERE meal_id = %s", (meal_id,))
            for item in req.items:
                conn.execute(
                    "INSERT INTO meal_items (meal_id, name, serving_size, calories, "
                    "protein_g, carbs_g, fat_g) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (meal_id, item.name, item.serving_size, item.calories,
                     item.protein_g, item.carbs_g, item.fat_g),
                )

    return {"status": "updated", "meal_id": meal_id}


@router.delete("/meals/{meal_id}")
async def delete_meal_endpoint(meal_id: int, user: CurrentUser = Depends(require_write)):
    """Delete a meal and its items."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")
        conn.execute("DELETE FROM meal_logs WHERE id = %s", (meal_id,))
    return {"status": "ok"}


@router.post("/meals/{meal_id}/analyze")
async def analyze_meal_endpoint(meal_id: int, user: CurrentUser = Depends(require_write)):
    """Send a meal to the nutritionist agent for analysis and save the feedback."""
    from datetime import datetime, timezone
    from server.nutrition.agent import chat as nutrition_chat

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with get_db() as conn:
        # Rate limit check
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM meal_logs WHERE date = %s AND user_id = %s",
            (today, "athlete"),
        ).fetchone()
        if count_row and count_row["cnt"] >= DAILY_ANALYSIS_LIMIT:
            raise HTTPException(429, f"Daily analysis limit reached ({DAILY_ANALYSIS_LIMIT}/day).")

        row = conn.execute("SELECT * FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meal not found")
        meal = dict(row)
        items = get_meal_items(conn, meal_id)

    # Build analysis prompt
    item_lines = []
    for it in items:
        serving = f" ({it['serving_size']})" if it.get("serving_size") else ""
        item_lines.append(
            f"  - {it['name']}{serving}: "
            f"{it['calories']} kcal, P{it['protein_g']}g / C{it['carbs_g']}g / F{it['fat_g']}g"
        )
    items_text = "\n".join(item_lines) or "  No itemized breakdown available."

    prompt = (
        f"Analyze this meal and provide nutritionist feedback. "
        f"Do NOT call any tools — just provide your analysis as text.\n\n"
        f"Meal: {meal['description']}\n"
        f"Totals: {meal['total_calories']} kcal, "
        f"P{meal['total_protein_g']}g / C{meal['total_carbs_g']}g / F{meal['total_fat_g']}g\n"
        f"Confidence: {meal['confidence']}\n"
        f"Items:\n{items_text}"
    )
    if meal.get("user_notes"):
        prompt += f"\nUser notes: {meal['user_notes']}"

    session_id = str(uuid.uuid4())

    # Include photo if available
    image_bytes = None
    image_mime = None
    if meal.get("photo_gcs_path"):
        photo_data = download_photo(meal["photo_gcs_path"])
        if photo_data:
            image_bytes = photo_data
            image_mime = "image/jpeg"

    try:
        response_text, _, _ = await nutrition_chat(
            message=prompt,
            user_id=user.email if hasattr(user, "email") else "athlete",
            session_id=session_id,
            user=user,
            image_data=image_bytes,
            image_mime_type=image_mime,
        )
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            raise HTTPException(429, "The AI model is currently busy. Please try again in a moment.")
        raise

    # Save analysis to agent_notes
    with get_db() as conn:
        conn.execute(
            "UPDATE meal_logs SET agent_notes = %s WHERE id = %s",
            (response_text, meal_id),
        )
        updated = conn.execute("SELECT * FROM meal_logs WHERE id = %s", (meal_id,)).fetchone()

    result = dict(updated)
    result["photo_url"] = _photo_url(meal_id, bool(result.get("photo_gcs_path")))
    return result


# ---------------------------------------------------------------------------
# Daily / Weekly Summaries
# ---------------------------------------------------------------------------

@router.get("/daily-summary")
async def daily_summary(
    date: str = "",
    user: CurrentUser = Depends(require_read),
    tz: ZoneInfo = Depends(get_client_tz),
):
    """Get aggregated macros and caloric balance for a date."""
    from server.utils.dates import user_today
    if not date:
        date = user_today(tz)

    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        targets = get_macro_targets(conn)

        tz_name = str(tz)
        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides "
            "WHERE (start_time::TIMESTAMPTZ AT TIME ZONE %s)::DATE = %s::DATE",
            (tz_name, date),
        ).fetchone()
        ride_cal = int(ride_row["total"]) if ride_row else 0

    from server.nutrition.tools import _estimate_daily_bmr
    bmr = _estimate_daily_bmr()
    total_out = ride_cal + bmr
    cal_in = int(totals["calories"])

    return {
        "date": date,
        "total_calories_in": cal_in,
        "total_protein_g": round(float(totals["protein_g"]), 1),
        "total_carbs_g": round(float(totals["carbs_g"]), 1),
        "total_fat_g": round(float(totals["fat_g"]), 1),
        "meal_count": int(totals["meal_count"]),
        "target_calories": targets["calories"],
        "target_protein_g": targets["protein_g"],
        "target_carbs_g": targets["carbs_g"],
        "target_fat_g": targets["fat_g"],
        "remaining_calories": targets["calories"] - cal_in,
        "calories_out": {"rides": ride_cal, "estimated_bmr": bmr, "total": total_out},
        "net_caloric_balance": cal_in - total_out,
    }


@router.get("/weekly-summary")
async def weekly_summary_endpoint(date: str = "", user: CurrentUser = Depends(require_read)):
    """Get 7-day breakdown with daily totals and weekly averages."""
    from server.nutrition.tools import get_weekly_summary
    return get_weekly_summary(date)


# ---------------------------------------------------------------------------
# Meal Plan (planned meals)
# ---------------------------------------------------------------------------

MEAL_SLOT_ORDER = [
    "breakfast", "snack_am", "lunch", "snack_pm",
    "pre_workout", "post_workout", "dinner",
]


def _build_meal_plan_day(date: str, planned_rows: list[dict], actual_rows: list[dict]) -> dict:
    """Build a MealPlanDay response from raw planned and actual meal rows."""
    import json

    planned_by_slot = {}
    for r in planned_rows:
        items_parsed = None
        if r.get("items"):
            try:
                items_parsed = json.loads(r["items"])
            except (json.JSONDecodeError, TypeError):
                items_parsed = None
        planned_by_slot[r["meal_slot"]] = {
            "id": r["id"],
            "user_id": r.get("user_id", "athlete"),
            "date": str(r["date"]),
            "meal_slot": r["meal_slot"],
            "name": r["name"],
            "description": r.get("description"),
            "total_calories": r["total_calories"],
            "total_protein_g": r["total_protein_g"],
            "total_carbs_g": r["total_carbs_g"],
            "total_fat_g": r["total_fat_g"],
            "items": items_parsed,
            "agent_notes": r.get("agent_notes"),
            "created_at": r.get("created_at"),
        }

    actual = [
        {
            "id": m["id"],
            "date": m["date"],
            "logged_at": m["logged_at"],
            "meal_type": m.get("meal_type"),
            "description": m["description"],
            "total_calories": m["total_calories"],
            "total_protein_g": m["total_protein_g"],
            "total_carbs_g": m["total_carbs_g"],
            "total_fat_g": m["total_fat_g"],
            "confidence": m["confidence"],
            "photo_url": _photo_url(m["id"], bool(m.get("photo_gcs_path"))),
            "edited_by_user": m.get("edited_by_user", False),
            "user_notes": m.get("user_notes"),
            "agent_notes": m.get("agent_notes"),
        }
        for m in actual_rows
    ]

    planned_cal = sum(r["total_calories"] for r in planned_rows)
    planned_p = sum(r["total_protein_g"] for r in planned_rows)
    planned_c = sum(r["total_carbs_g"] for r in planned_rows)
    planned_f = sum(r["total_fat_g"] for r in planned_rows)

    actual_cal = sum(m["total_calories"] for m in actual_rows)
    actual_p = sum(m["total_protein_g"] for m in actual_rows)
    actual_c = sum(m["total_carbs_g"] for m in actual_rows)
    actual_f = sum(m["total_fat_g"] for m in actual_rows)

    return {
        "date": date,
        "planned": planned_by_slot,
        "actual": actual,
        "day_totals": {
            "planned_calories": planned_cal,
            "actual_calories": actual_cal,
            "planned_protein_g": round(planned_p, 1),
            "actual_protein_g": round(actual_p, 1),
            "planned_carbs_g": round(planned_c, 1),
            "actual_carbs_g": round(actual_c, 1),
            "planned_fat_g": round(planned_f, 1),
            "actual_fat_g": round(actual_f, 1),
        },
    }


@router.get("/meal-plan")
async def get_meal_plan(
    date: str = "",
    days: int = 7,
    user: CurrentUser = Depends(require_read),
):
    """Get weekly meal plan with plan-vs-actual per day."""
    from datetime import datetime, timedelta
    from server.utils.dates import user_today
    if not date:
        date = user_today()

    start_dt = datetime.fromisoformat(date)
    end_dt = start_dt + timedelta(days=days - 1)
    end_str = end_dt.strftime("%Y-%m-%d")

    with get_db() as conn:
        planned_rows = get_planned_meals_for_range(conn, date, end_str)
        # Get actual meals for the same range
        actual_rows = conn.execute(
            "SELECT * FROM meal_logs WHERE user_id = %s AND date >= %s AND date <= %s "
            "ORDER BY date, logged_at",
            ("athlete", date, end_str),
        ).fetchall()
        actual_rows = [dict(r) for r in actual_rows]

    # Group by date
    planned_by_date: dict[str, list] = {}
    for r in planned_rows:
        planned_by_date.setdefault(str(r["date"]), []).append(r)

    actual_by_date: dict[str, list] = {}
    for r in actual_rows:
        actual_by_date.setdefault(str(r["date"]), []).append(r)

    # Build response for each day in range
    result_days = []
    for i in range(days):
        d = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        day_planned = planned_by_date.get(d, [])
        day_actual = actual_by_date.get(d, [])
        result_days.append(_build_meal_plan_day(d, day_planned, day_actual))

    return {
        "start_date": date,
        "end_date": end_str,
        "days": result_days,
    }


@router.get("/meal-plan/{date}")
async def get_meal_plan_day(date: str, user: CurrentUser = Depends(require_read)):
    """Get a single day's planned vs actual meals."""
    with get_db() as conn:
        planned_rows = get_planned_meals_for_date(conn, date)
        actual_rows = get_meals_for_date(conn, date)

    return _build_meal_plan_day(date, planned_rows, actual_rows)


@router.delete("/meal-plan/{date}")
async def delete_meal_plan(
    date: str,
    meal_slot: str = "",
    user: CurrentUser = Depends(require_write),
):
    """Clear planned meals for a date, or a specific slot."""
    from server.nutrition.planning_tools import ALLOWED_MEAL_SLOTS

    if meal_slot and meal_slot not in ALLOWED_MEAL_SLOTS:
        raise HTTPException(400, f"Invalid meal_slot. Must be one of: {', '.join(sorted(ALLOWED_MEAL_SLOTS))}")

    with get_db() as conn:
        if meal_slot:
            result = conn.execute(
                "DELETE FROM planned_meals WHERE user_id = %s AND date = %s AND meal_slot = %s",
                ("athlete", date, meal_slot),
            )
        else:
            result = conn.execute(
                "DELETE FROM planned_meals WHERE user_id = %s AND date = %s",
                ("athlete", date),
            )
        removed = result.rowcount

    return {"status": "ok", "date": date, "meal_slot": meal_slot or "all", "removed": removed}


# ---------------------------------------------------------------------------
# Dietary Preferences
# ---------------------------------------------------------------------------

@router.get("/preferences")
async def get_preferences(user: CurrentUser = Depends(require_read)):
    """Get dietary preferences and nutritionist principles."""
    from server.database import get_setting
    return {
        "dietary_preferences": get_setting("dietary_preferences"),
        "nutritionist_principles": get_setting("nutritionist_principles"),
    }


@router.put("/preferences")
async def update_preferences(req: DietaryPreferencesUpdate, user: CurrentUser = Depends(require_write)):
    """Update dietary preferences or nutritionist principles."""
    from server.database import set_setting

    valid_sections = {"dietary_preferences", "nutritionist_principles"}
    if req.section not in valid_sections:
        raise HTTPException(400, f"Invalid section. Must be one of: {', '.join(sorted(valid_sections))}")

    set_setting(req.section, req.value)
    return {"status": "updated", "section": req.section}


# ---------------------------------------------------------------------------
# Macro Targets
# ---------------------------------------------------------------------------

@router.get("/targets")
async def get_targets(user: CurrentUser = Depends(require_read)):
    """Get current daily macro targets."""
    with get_db() as conn:
        return get_macro_targets(conn)


@router.put("/targets")
async def update_targets(req: MacroTargets, user: CurrentUser = Depends(require_write)):
    """Update daily macro targets."""
    if req.calories <= 0 or req.calories > 10000:
        raise HTTPException(400, "calories must be between 1 and 10000")
    if req.protein_g < 0 or req.carbs_g < 0 or req.fat_g < 0:
        raise HTTPException(400, "Macro targets must be non-negative")

    with get_db() as conn:
        conn.execute(
            "INSERT INTO macro_targets (user_id, calories, protein_g, carbs_g, fat_g, updated_at) "
            "VALUES ('athlete', %s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "calories = EXCLUDED.calories, protein_g = EXCLUDED.protein_g, "
            "carbs_g = EXCLUDED.carbs_g, fat_g = EXCLUDED.fat_g, "
            "updated_at = EXCLUDED.updated_at",
            (req.calories, req.protein_g, req.carbs_g, req.fat_g),
        )
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Nutritionist Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=NutritionChatResponse)
async def nutrition_chat_endpoint(req: NutritionChatRequest, user: CurrentUser = Depends(require_read)):
    """Send a message to the nutritionist agent."""
    from server.nutrition.agent import chat as nutrition_chat

    session_id = req.session_id or str(uuid.uuid4())

    # Decode base64 image if provided
    image_bytes = None
    if req.image_data:
        image_bytes = base64.b64decode(req.image_data)

    try:
        response_text, requires_clarification, meal_saved = await nutrition_chat(
            message=req.message,
            session_id=session_id,
            user=user,
            image_data=image_bytes,
            image_mime_type=req.image_mime_type,
        )
    except Exception as e:
        if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
            raise HTTPException(429, "The AI model is currently busy. Please try again in a moment.")
        raise

    return NutritionChatResponse(
        response=response_text,
        session_id=session_id,
        requires_clarification=requires_clarification,
        meal_saved=meal_saved,
    )


# ---------------------------------------------------------------------------
# Nutritionist Sessions -- same pattern as server/routers/coaching.py:31-88
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[SessionSummary])
async def list_nutrition_sessions(user: CurrentUser = Depends(require_read)):
    """List nutritionist chat sessions."""
    with get_db() as conn:
        # ADK stores sessions with app_name; filter by our app
        # The DbSessionService uses chat_sessions table
        rows = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions "
            "WHERE session_type = 'nutrition' ORDER BY updated_at DESC"
        ).fetchall()

    return [
        SessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_nutrition_session(session_id: str, user: CurrentUser = Depends(require_read)):
    """Get a nutritionist session with messages."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()

        if not row:
            raise HTTPException(404, "Session not found")

        events = conn.execute(
            "SELECT author, role, content_text, timestamp FROM chat_events "
            "WHERE session_id = %s ORDER BY id",
            (session_id,),
        ).fetchall()

    return SessionDetail(
        session_id=row["session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        messages=[
            SessionMessage(
                author=e["author"], role=e["role"],
                content_text=e["content_text"], timestamp=e["timestamp"],
            )
            for e in events
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_nutrition_session(session_id: str, user: CurrentUser = Depends(require_write)):
    """Delete a nutritionist session."""
    with get_db() as conn:
        conn.execute("DELETE FROM chat_events WHERE session_id = %s", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
    return {"status": "deleted"}
