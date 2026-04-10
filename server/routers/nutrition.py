"""Nutrition meal logging and Nutritionist chat endpoints."""

import uuid
import base64
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException

from server.auth import CurrentUser, require_read, require_write
from server.models.schemas import (
    MealSummary, MealDetail, MealItem, MacroTargets,
    DailyNutritionSummary, MealUpdateRequest,
    NutritionChatRequest, NutritionChatResponse,
    SessionSummary, SessionDetail, SessionMessage,
)
from server.database import get_db
from server.queries import get_meals_for_date, get_meal_items, get_macro_targets, get_daily_meal_totals
from server.nutrition.photo import upload_meal_photo, generate_photo_url

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

DAILY_ANALYSIS_LIMIT = 20


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
        response_text = await nutrition_chat(
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
            return {"status": "analysis_only", "response": response_text, "photo_url": generate_photo_url(gcs_path)}

        meal = dict(row)
        items = get_meal_items(conn, meal["id"])

    meal["photo_url"] = generate_photo_url(gcs_path)
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
        m["photo_url"] = generate_photo_url(m.get("photo_gcs_path", ""))
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
    meal["photo_url"] = generate_photo_url(meal.get("photo_gcs_path", ""))
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

        if updates:
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


# ---------------------------------------------------------------------------
# Daily / Weekly Summaries
# ---------------------------------------------------------------------------

@router.get("/daily-summary")
async def daily_summary(date: str = "", user: CurrentUser = Depends(require_read)):
    """Get aggregated macros and caloric balance for a date."""
    from datetime import datetime
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        totals = get_daily_meal_totals(conn, date)
        targets = get_macro_targets(conn)

        ride_row = conn.execute(
            "SELECT COALESCE(SUM(total_calories), 0) AS total FROM rides WHERE date = %s",
            (date,),
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
        response = await nutrition_chat(
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

    return NutritionChatResponse(response=response, session_id=session_id)


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
            "WHERE session_id LIKE %s ORDER BY updated_at DESC",
            ("nutrition-%",),
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
