"""ADK-based coaching agent setup."""

import functools

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.genai import types

from server.config import GEMINI_MODEL, GCP_PROJECT, GCP_LOCATION
from server.database import get_setting
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
)
from server.coaching.planning_tools import (
    replan_missed_day,
    generate_weekly_plan,
    adjust_phase,
    regenerate_phase_workouts,
    replace_workout,
    list_workout_templates,
    save_workout_template,
    get_week_summary,
    sync_workouts_to_garmin,
    update_coach_settings,
    set_workout_coach_notes,
    set_ride_coach_comments,
)

APP_NAME = "cycling-coach"

# Singleton instances
_session_service = None
_memory_service = None
_runner = None

# Write tools that require readwrite/admin role
_WRITE_TOOLS = {
    replan_missed_day,
    generate_weekly_plan,
    adjust_phase,
    regenerate_phase_workouts,
    replace_workout,
    save_workout_template,
    sync_workouts_to_garmin,
    update_coach_settings,
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
    from server.database import get_all_settings
    settings = get_all_settings()

    today = datetime.now()
    today_str = today.strftime("%A, %B %d, %Y")  # e.g. "Friday, March 28, 2026"
    today_iso = today.strftime("%Y-%m-%d")

    return f"""You are an expert cycling coach working with a specific athlete.

TODAY'S DATE: {today_str} ({today_iso})
Use this date to correctly map day-of-week references (e.g. "Saturday", "today", "next Tuesday") to YYYY-MM-DD date strings when calling tools.

ATHLETE PROFILE:
{settings['athlete_profile']}

KEY COACHING PRINCIPLES:
{settings['coaching_principles']}

YOUR ROLE:
{settings['coach_role']}

PLAN MANAGEMENT:
{settings['plan_management']}"""


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
    # Wrap write tools with permission gate
    tools = [
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
        get_week_summary,
        list_workout_templates,
        preload_memory_tool,
    ]
    for fn in _WRITE_TOOLS:
        tools.append(_permission_gate(fn))

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


async def chat(message: str, user_id: str = "athlete", session_id: str = "default", user=None) -> str:
    """Send a message to the coaching agent and get a response."""
    import os

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
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and event.author == "cycling_coach":
                    response_text += part.text

    # Save session to long-term memory after each interaction
    updated_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if updated_session:
        await memory_service.add_session_to_memory(updated_session)

    return response_text or "I couldn't generate a response. Please try again."
