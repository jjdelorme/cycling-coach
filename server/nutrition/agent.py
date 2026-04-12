"""ADK-based Nutritionist agent setup."""

import functools
import time
import threading

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools import google_search
from google.genai import types

from server.config import GEMINI_MODEL, GCP_PROJECT, GCP_LOCATION
from server.database import get_setting
from server.logging_config import get_logger, get_trace_id
from server.telemetry import get_tracer
from server.coaching.session_service import DbSessionService
from server.coaching.memory_service import DbMemoryService
from server.nutrition.tools import (
    get_meal_history,
    get_daily_macros,
    get_weekly_summary,
    get_caloric_balance,
    get_macro_targets_tool,
    get_upcoming_training_load,
    get_recent_workouts,
    get_planned_meals,
    get_dietary_preferences,
)
from server.nutrition.planning_tools import (
    save_meal_analysis,
    update_meal,
    delete_meal,
    set_macro_targets,
    generate_meal_plan,
    replace_planned_meal,
    clear_meal_plan,
    update_dietary_preferences,
    ask_clarification,
)

APP_NAME = "nutrition-coach"

logger = get_logger(__name__)
_tracer = get_tracer(__name__)

# Singleton instances
_session_service = None
_memory_service = None
_runner = None

# Write tools that require readwrite/admin role
_WRITE_TOOLS = {
    save_meal_analysis,
    update_meal,
    delete_meal,
    set_macro_targets,
    generate_meal_plan,
    replace_planned_meal,
    clear_meal_plan,
    update_dietary_preferences,
}

# Thread-local storage for current user role during agent execution
_current_user_role = threading.local()


def _permission_gate(fn):
    """Wrap a write tool to check the caller's role before executing."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        role = getattr(_current_user_role, "role", "admin")
        if role not in ("readwrite", "admin"):
            return {"error": "You don't have write permissions. Ask an administrator to upgrade your access."}
        return fn(*args, **kwargs)
    return wrapper


def _build_system_instruction(ctx) -> str:
    """Build the nutritionist system instruction dynamically from DB state."""
    from datetime import datetime, timedelta
    from server.database import get_all_athlete_settings, get_db
    from server.queries import get_current_pmc_row, get_macro_targets
    from server.services.weight import get_current_weight

    settings = get_all_athlete_settings()
    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")
    today_iso = today.strftime("%Y-%m-%d")

    try:
        ftp = float(settings.get("ftp", 0))
    except (ValueError, TypeError):
        ftp = 0.0

    with get_db() as conn:
        weight_kg = get_current_weight(conn)
        pmc = get_current_pmc_row(conn)
        targets = get_macro_targets(conn)

        # Recent meals (last 3 days)
        three_days_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")
        recent_meals = conn.execute(
            "SELECT date, logged_at, description, total_calories, total_protein_g, "
            "total_carbs_g, total_fat_g FROM meal_logs WHERE date >= %s "
            "AND user_id = %s ORDER BY date DESC, logged_at DESC LIMIT 15",
            (three_days_ago, "athlete"),
        ).fetchall()

        # Recent rides (last 3 days)
        recent_rides = conn.execute(
            "SELECT date, sub_sport, duration_s, tss, total_calories "
            "FROM rides WHERE date >= %s ORDER BY date DESC LIMIT 5",
            (three_days_ago,),
        ).fetchall()

    ctl = round(pmc["ctl"], 1) if pmc and pmc.get("ctl") is not None else "N/A"

    recent_meals_text = "\n".join([
        f"  - {m['date']} {m['logged_at'][-8:-3]}: {m['description']} -- "
        f"{m['total_calories']} kcal (P{round(m['total_protein_g'])}g / "
        f"C{round(m['total_carbs_g'])}g / F{round(m['total_fat_g'])}g)"
        for m in recent_meals
    ]) or "  No meals logged recently."

    recent_rides_text = "\n".join([
        f"  - {r['date']}: {r['sub_sport'] or 'ride'}, "
        f"{round((r['duration_s'] or 0) / 3600, 1)}h, "
        f"TSS {r['tss'] or '?'}, {r['total_calories'] or '?'} kcal"
        for r in recent_rides
    ]) or "  No recent rides."

    dietary_prefs = get_setting("dietary_preferences")
    nutritionist_principles = get_setting("nutritionist_principles")

    return f"""You are an expert sports nutritionist working with an endurance cyclist.

TODAY'S DATE: {today_str} ({today_iso})

ATHLETE PROFILE:
- Weight: {weight_kg} kg / FTP: {int(ftp)} W / Current CTL: {ctl}
- Daily targets: {targets['calories']} kcal (P {targets['protein_g']}g / C {targets['carbs_g']}g / F {targets['fat_g']}g)

DIETARY PREFERENCES:
{dietary_prefs}

NUTRITIONIST PRINCIPLES:
{nutritionist_principles}

RECENT MEALS (last 3 days):
{recent_meals_text}

RECENT TRAINING (last 3 days):
{recent_rides_text}

YOUR ROLE:
1. Analyze meal photos and estimate macros accurately
2. Track daily and weekly intake trends
3. Identify patterns (repeated meals, nutrient gaps, timing issues)
4. Provide fueling guidance for upcoming workouts
5. Flag concerning patterns (chronic under-fueling, excessive deficit)
6. Create and manage meal plans that align with training load

MEAL PHOTO ANALYSIS PROTOCOL:
When you receive a meal photo:
1. IDENTIFY each distinct food item visible
2. ESTIMATE portion sizes using visual cues (plate size, utensils, depth/density)
3. For each item, estimate serving size and macros
4. SUM totals. Assign CONFIDENCE (high/medium/low)
5. If LOW confidence, call ask_clarification before saving
6. If MEDIUM or HIGH, call save_meal_analysis directly
7. Before analyzing, check get_meal_history for similar past meals as baselines

TRAINING CONTEXT PROTOCOL:
NEVER ask the athlete whether they have a ride planned or what their training looks like — you have tools for this.
- When fueling guidance, pre/post-workout nutrition, or ride context is relevant: call get_upcoming_training_load FIRST.
- When recent training history or recovery context is relevant: call get_recent_workouts FIRST.
Use the data from those tools to give specific, data-driven advice without interrogating the athlete.

MEAL PLANNING PROTOCOL:
When creating meal plans:
1. Call get_upcoming_training_load to see planned rides and estimated caloric burn
2. Call get_dietary_preferences to check dietary constraints and preferences
3. Call get_planned_meals to see what's already planned (avoid duplicating)
4. Periodize nutrition per training load:
   - Heavy days (TSS > 80): increase carbs, add pre_workout/post_workout meals
   - Moderate days (TSS 40-80): standard macro targets
   - Rest days: reduce carbs, maintain protein at 1.6-2.0 g/kg
5. Call generate_meal_plan to persist — NEVER just verbally suggest meals
6. Provide agent_notes explaining training context for each meal
7. Valid meal_slot values: breakfast, lunch, dinner, snack_am, snack_pm, pre_workout, post_workout
Use replace_planned_meal for single-slot changes, clear_meal_plan to remove plans.

NO LAWYERLY DISCLAIMERS:
You are the professional. Do NOT use "assistant-style" legalistic language. 
- NEVER tell the athlete to "check the label," "consult a doctor," or "consult a professional." 
- NEVER use phrases like "formulations may shift" or "I always recommend verifying."
Give your best expert advice based on the data. You are the professional; act like it.

HIGH-AGENCY DATA PROTOCOL:
NEVER ask the athlete for information that your tools can provide. 
- Before asking "Do you have your meals planned?", you MUST call get_planned_meals.
- Before asking "What is your training?", you MUST call get_upcoming_training_load.
If the data exists, use it to make a proactive recommendation instead of asking permission to help.

COMMUNICATION STYLE:
- Zero conversational filler or "chit-chat." 
- Lead with data and proactive recommendations.
- Don't ask "Would you like..." — provide the expert suggestion immediately if the data shows a need (e.g., a caloric deficit or unplanned meal slot).
- Professional-to-professional tone. No lecturing.
- Concise, specific with numbers. Reference specific numbers from history when making recommendations.
- Lead with macro summary, then details."""


def _get_effective_model() -> str:
    """Return the Gemini model, preferring DB setting over env var default."""
    db_model = get_setting("gemini_model")
    return db_model if db_model else GEMINI_MODEL


def reset_runner():
    """Reset cached runner so the next chat() picks up new settings."""
    global _runner, _session_service, _memory_service
    _runner = None
    _session_service = None
    _memory_service = None


def _get_agent():
    tools = [
        get_meal_history,
        get_daily_macros,
        get_weekly_summary,
        get_caloric_balance,
        get_macro_targets_tool,
        get_upcoming_training_load,
        get_recent_workouts,
        get_planned_meals,
        get_dietary_preferences,
        ask_clarification,
    ]
    for fn in _WRITE_TOOLS:
        tools.append(_permission_gate(fn))

    return Agent(
        name="nutritionist",
        model=_get_effective_model(),
        description="Sports nutritionist specializing in endurance athlete fueling",
        instruction=_build_system_instruction,
        tools=tools,
    )


def get_nutritionist_agent() -> Agent:
    """Return the Nutritionist Agent instance for use as an AgentTool.

    Called by the Cycling Coach's agent setup to wire the Nutritionist
    as a delegatable tool. The Agent object is re-created each time to
    pick up any settings changes (model, etc).
    """
    return _get_agent()


def get_runner():
    global _session_service, _runner, _memory_service
    if _runner is None:
        _session_service = DbSessionService()
        _memory_service = DbMemoryService()
        _runner = Runner(
            agent=_get_agent(),
            app_name=APP_NAME,
            session_service=_session_service,
            memory_service=_memory_service,
        )
    return _runner, _session_service, _memory_service


async def chat(
    message: str,
    user_id: str = "athlete",
    session_id: str = "default",
    user=None,
    image_data: bytes | None = None,
    image_mime_type: str | None = None,
    photo_gcs_path: str = "",
    audio_data: bytes | None = None,
    audio_mime_type: str | None = None,
) -> str:
    """Send a message (optionally with image and/or audio) to the nutritionist agent.

    When image_data is provided, constructs a multimodal Content with both
    image and text parts -- the agent sees the photo directly via Gemini's
    vision capability. When audio_data is provided, adds an audio Part so
    the agent can hear the user's voice note describing the meal.
    """
    import os

    trace_id = get_trace_id()
    t0 = time.monotonic()

    logger.info(
        "nutritionist_chat_start",
        session_id=session_id,
        user_id=user_id,
        user_role=user.role if user else "admin",
        message_len=len(message),
        has_image=image_data is not None,
        has_audio=audio_data is not None,
        trace_id=trace_id,
    )

    # Auth config -- same pattern as server/coaching/agent.py:270-283
    db_api_key = get_setting("gemini_api_key")
    db_location = get_setting("gcp_location")

    if db_api_key:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
        os.environ["GOOGLE_API_KEY"] = db_api_key
    else:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT)

    effective_location = db_location if db_location else GCP_LOCATION
    os.environ["GOOGLE_CLOUD_LOCATION"] = effective_location

    if user is not None:
        _current_user_role.role = user.role
    else:
        _current_user_role.role = "admin"

    runner, session_service, memory_service = get_runner()

    # Ensure session exists
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    # Build Content -- multimodal if image/audio provided (Q1 decision: YES)
    parts = []
    if image_data and image_mime_type:
        parts.append(types.Part.from_bytes(data=image_data, mime_type=image_mime_type))
        # Inject photo_gcs_path context so save_meal_analysis knows where the photo is
        if photo_gcs_path:
            message = f"[Photo stored at: {photo_gcs_path}]\n{message}"

    # Audio part — passed directly to Gemini as multimodal input
    if audio_data and audio_mime_type:
        parts.append(types.Part.from_bytes(data=audio_data, mime_type=audio_mime_type))

    parts.append(types.Part.from_text(text=message))

    content = types.Content(role="user", parts=parts)

    response_text = ""
    tool_calls: list[str] = []

    with _tracer.start_as_current_span("nutritionist.chat") as chat_span:
        chat_span.set_attribute("session_id", session_id)
        chat_span.set_attribute("user_id", user_id)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fn_name = part.function_call.name
                        tool_calls.append(fn_name)
                        with _tracer.start_as_current_span("nutritionist.tool_call") as tool_span:
                            tool_span.set_attribute("tool_name", fn_name)
                        logger.debug("nutritionist_tool_call", tool=fn_name, session_id=session_id, trace_id=trace_id)
                    elif hasattr(part, "function_response") and part.function_response:
                        logger.debug("nutritionist_tool_response", tool=part.function_response.name, session_id=session_id, trace_id=trace_id)
                    elif part.text and event.author == "nutritionist":
                        response_text += part.text

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "nutritionist_chat_complete",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        latency_ms=round(elapsed_ms, 1),
        tool_calls=tool_calls,
        tool_call_count=len(tool_calls),
        response_len=len(response_text),
        success=bool(response_text),
    )

    # Save session to long-term memory
    updated_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if updated_session:
        await memory_service.add_session_to_memory(updated_session)

    return response_text or "I couldn't generate a response. Please try again."
