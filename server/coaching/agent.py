from server.utils.adk import json_safe_tool
"""ADK-based coaching agent setup."""

import functools
import time

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.adk.tools import google_search
from google.genai import types

from server.config import GEMINI_MODEL, GCP_PROJECT, GCP_LOCATION
from server.database import get_setting
from server.logging_config import get_logger, get_trace_id
from server.telemetry import get_tracer
from server.coaching.session_service import DbSessionService
from server.coaching.memory_service import DbMemoryService
from server.coaching.tools import (
    get_pmc_metrics,
    get_recent_rides,
    get_upcoming_workouts,
    get_power_bests,
    get_training_summary,
    get_ftp_history,
    get_periodization_status,
    get_ride_analysis,
    get_ride_segments,
    get_ride_records_window,
    get_power_curve,
    get_athlete_status,
    get_planned_workout_for_ride,
    get_athlete_nutrition_status,
)
from server.nutrition.agent import get_nutritionist_agent
from server.coaching.planning_tools import (
    replan_missed_day,
    generate_week_from_spec,
    adjust_phase,
    replace_workout,
    list_workout_templates,
    save_workout_template,
    get_week_summary,
    sync_workouts_to_garmin,
    update_coach_settings,
    update_athlete_setting,
    set_workout_coach_notes,
    set_ride_coach_comments,
)

APP_NAME = "cycling-coach"

logger = get_logger(__name__)
_tracer = get_tracer(__name__)

# Singleton instances
_session_service = None
_memory_service = None
_runner = None

# Write tools that require readwrite/admin role
_WRITE_TOOLS = {
    replan_missed_day,
    generate_week_from_spec,
    adjust_phase,
    replace_workout,
    save_workout_template,
    sync_workouts_to_garmin,
    update_coach_settings,
    update_athlete_setting,
    set_workout_coach_notes,
    set_ride_coach_comments,
}

# Thread-local storage for current user role during agent execution
import threading
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
    """Build the system instruction dynamically from database settings."""
    from datetime import datetime
    from server.database import get_all_settings, get_all_athlete_settings, get_db
    from server.queries import get_current_pmc_row
    from server.utils.dates import get_request_tz
    from server.services.weight import get_current_weight
    settings = get_all_settings()
    benchmarks = get_all_athlete_settings()

    tz = get_request_tz()
    today = datetime.now(tz)
    today_str = today.strftime("%A, %B %d, %Y")  # e.g. "Friday, March 28, 2026"
    today_iso = today.strftime("%Y-%m-%d")

    # Compute derived metrics
    try:
        ftp = float(benchmarks.get("ftp", 0))
    except (ValueError, TypeError):
        ftp = 0.0

    # Resolve weight via priority chain (Withings → ride → settings → default)
    with get_db() as conn:
        weight_kg = get_current_weight(conn)
    # Keep benchmarks dict consistent so formatted output reflects resolved weight
    benchmarks["weight_kg"] = str(weight_kg)

    weight_lbs = round(weight_kg * 2.20462, 1) if weight_kg > 0 else 0.0
    w_kg = round(ftp / weight_kg, 2) if weight_kg > 0 else 0.0

    # Format structured benchmarks for the coach
    labels = {
        "ftp": "Current FTP (Watts)",
        "weight_kg": "Current Weight (kg)",
        "lthr": "Lactate Threshold HR (bpm)",
        "max_hr": "Max Heart Rate (bpm)",
        "resting_hr": "Resting Heart Rate (bpm)",
        "age": "Age (years)",
        "gender": "Gender",
    }
    benchmarks_text = "\n".join([
        f"- {labels.get(k, k)}: {v}"
        for k, v in benchmarks.items()
        if k in labels
    ])

    # Add computed metrics
    benchmarks_text += f"\n- Current Weight (lbs): {weight_lbs}"
    benchmarks_text += f"\n- W/kg: {w_kg}"

    # Add PMC training load
    with get_db() as conn:
        pmc = get_current_pmc_row(conn)

    if pmc and pmc.get("ctl") is not None:
        benchmarks_text += f"\n- CTL (Fitness): {round(pmc['ctl'], 1)}"
        benchmarks_text += f"\n- ATL (Fatigue): {round(pmc['atl'], 1)}"
        benchmarks_text += f"\n- TSB (Form): {round(pmc['tsb'], 1)}"
        benchmarks_text += f"\n- Metrics as-of: {pmc['date']}"
    else:
        benchmarks_text += "\n- CTL/ATL/TSB: No data available"

    # Add last 7 days of rides for immediate adaptive context
    from datetime import timedelta
    seven_days_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    tz_name = get_request_tz().key
    with get_db() as conn:
        recent_rides = conn.execute(
            """SELECT (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE::TEXT AS date,
                      sub_sport, duration_s, tss, normalized_power
               FROM rides
               WHERE (start_time::TIMESTAMPTZ AT TIME ZONE ?)::DATE >= ?::DATE
               ORDER BY start_time DESC LIMIT 7""",
            (tz_name, tz_name, seven_days_ago),
        ).fetchall()

    if recent_rides:
        recent_lines = "\n".join([
            f"  - {r['date']}: {r['sub_sport'] or 'ride'}, "
            f"{round((r['duration_s'] or 0)/3600, 1)}h, "
            f"TSS {r['tss'] or '?'}, NP {r['normalized_power'] or '?'}w"
            for r in recent_rides
        ])
        recent_context = f"\n\nRECENT TRAINING (last 7 days — use this for adaptive decisions):\n{recent_lines}"
    else:
        recent_context = "\n\nRECENT TRAINING: No rides in last 7 days."

    return f"""You are an expert cycling coach working with a specific athlete.

TODAY'S DATE: {today_str} ({today_iso})
Use this date to correctly map day-of-week references (e.g. "Saturday", "today", "next Tuesday") to YYYY-MM-DD date strings when calling tools.

ATHLETE PERFORMANCE BENCHMARKS (Structured):
{benchmarks_text}

ATHLETE PROFILE (Free-text):
{settings['athlete_profile']}

KEY COACHING PRINCIPLES:
{settings['coaching_principles']}

YOUR ROLE:
{settings['coach_role']}

When analyzing a ride, use get_planned_workout_for_ride to compare what was planned vs what actually happened. Flag significant deviations in duration or TSS and suggest adjustments to the remaining week if needed.

COACH NOTES — MANDATORY:
Whenever you create or modify a planned workout (via replace_workout or generate_week_from_spec), you MUST provide personalized coaching notes. For replace_workout, call set_workout_coach_notes after creating the workout. For generate_week_from_spec, include coach_notes in each workout spec.

Write notes that are specific and actionable. Example of a GOOD note: "Recovery spin after Tuesday's hard threshold work — keep HR under 130bpm, cadence 90+, avoid any climbs. Goal is to flush the legs, not to train." Example of a BAD note: "Easy ride today." Never leave notes generic or blank when you have context about the athlete's recent training, upcoming events, or current form.

PLAN MANAGEMENT:
{settings['plan_management']}{recent_context}

NUTRITION INTEGRATION:
You have two ways to access the athlete's nutritional data:

1. QUICK CHECK — use get_athlete_nutrition_status (fast, direct DB query):
   - Has the athlete eaten today? How many calories so far?
   - What was their last meal?
   - Current caloric balance (in vs out)
   Use this for quick data checks before making coaching decisions.

2. COMPLEX FUELING GUIDANCE — delegate to the nutritionist agent (slower, full AI reasoning):
   - Pre-ride meal planning for rides > 2 hours
   - Recovery nutrition strategy after hard training blocks
   - Multi-day fueling plans for training camps or events
   - Analyzing whether chronic under-fueling is affecting performance
   The nutritionist has access to the full meal history, macro targets, and
   specialized knowledge about sports nutrition.

NUTRITION-AWARE COACH NOTES:
For workouts longer than 90 minutes, include fueling guidance in your coach notes:
1. Check the athlete's recent intake via get_athlete_nutrition_status
2. For rides > 2 hours, include:
   - Pre-ride meal recommendation (timing + approximate calories)
   - On-bike fueling target (typically 60-90g carbs/hour for endurance)
   - Post-ride recovery nutrition window
3. If the athlete's recent intake suggests under-fueling, flag this prominently
4. For particularly long or intense sessions (>3h or IF >0.85), delegate to
   the nutritionist for detailed fueling guidance"""


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
    # Regular function tools that need json wrapping
    raw_tools = [
        get_pmc_metrics,
        get_recent_rides,
        get_upcoming_workouts,
        get_power_bests,
        get_training_summary,
        get_ftp_history,
        get_periodization_status,
        get_ride_analysis,
        get_ride_segments,
        get_ride_records_window,
        get_power_curve,
        get_athlete_status,
        get_planned_workout_for_ride,
        get_athlete_nutrition_status,
        get_week_summary,
        list_workout_templates,
        preload_memory_tool,
    ]
    
    tools = [json_safe_tool(fn) for fn in raw_tools]
    
    # Add the AgentTool (which is a class instance, not a function, so it doesn't get wrapped)
    tools.append(AgentTool(agent=get_nutritionist_agent()))
    
    for fn in _WRITE_TOOLS:
        tools.append(json_safe_tool(_permission_gate(fn)))

    return Agent(
        name="cycling_coach",
        model=_get_effective_model(),
        description="Expert cycling coach",
        instruction=_build_system_instruction,
        tools=tools,
    )


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


async def chat(message: str, user_id: str = "athlete", session_id: str = "default", user=None, tz=None) -> str:
    """Send a message to the coaching agent and get a response."""
    import os

    trace_id = get_trace_id()
    t0 = time.monotonic()

    logger.info(
        "agent_chat_start",
        session_id=session_id,
        user_id=user_id,
        user_role=user.role if user else "admin",
        message_len=len(message),
        trace_id=trace_id,
    )

    # Check for API key in DB settings (overrides ADC auth)
    db_api_key = get_setting("gemini_api_key")
    db_location = get_setting("gcp_location")

    if db_api_key:
        # API key auth: use Google AI (not Vertex AI)
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
        os.environ["GOOGLE_API_KEY"] = db_api_key
    else:
        # Default: ADC via Vertex AI
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT)

    effective_location = db_location if db_location else GCP_LOCATION
    os.environ["GOOGLE_CLOUD_LOCATION"] = effective_location

    # Set the current user's role for permission gating on write tools
    if user is not None:
        _current_user_role.role = user.role
    else:
        _current_user_role.role = "admin"

    from server.utils.dates import set_request_tz
    from zoneinfo import ZoneInfo
    set_request_tz(tz if tz is not None else ZoneInfo("UTC"))

    runner, session_service, memory_service = get_runner()

    # Ensure session exists
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    )

    response_text = ""
    tool_calls: list[str] = []

    with _tracer.start_as_current_span("agent.chat") as chat_span:
        chat_span.set_attribute("session_id", session_id)
        chat_span.set_attribute("user_id", user_id)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            # Track tool calls for the trace log
            if event.content and event.content.parts:
                for part in event.content.parts:
                    # Tool call (function call)
                    if hasattr(part, "function_call") and part.function_call:
                        fn_name = part.function_call.name
                        tool_calls.append(fn_name)
                        with _tracer.start_as_current_span("agent.tool_call") as tool_span:
                            tool_span.set_attribute("tool_name", fn_name)
                        logger.debug(
                            "agent_tool_call",
                            tool=fn_name,
                            session_id=session_id,
                            trace_id=trace_id,
                        )
                    # Tool response
                    elif hasattr(part, "function_response") and part.function_response:
                        logger.debug(
                            "agent_tool_response",
                            tool=part.function_response.name,
                            session_id=session_id,
                            trace_id=trace_id,
                        )
                    # Final text response
                    elif part.text and event.author == "cycling_coach":
                        response_text += part.text

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "agent_chat_complete",
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        latency_ms=round(elapsed_ms, 1),
        tool_calls=tool_calls,
        tool_call_count=len(tool_calls),
        response_len=len(response_text),
        success=bool(response_text),
    )

    # Save session to long-term memory after each interaction
    updated_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if updated_session:
        await memory_service.add_session_to_memory(updated_session)

    return response_text or "I couldn't generate a response. Please try again."
