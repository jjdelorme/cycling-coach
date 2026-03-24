"""ADK-based coaching agent setup."""

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.tools.preload_memory_tool import preload_memory_tool
from google.genai import types

from server.config import GEMINI_MODEL, GCP_PROJECT, GCP_LOCATION
from server.coaching.sqlite_session_service import SqliteSessionService
from server.coaching.sqlite_memory_service import SqliteMemoryService
from server.coaching.tools import (
    get_pmc_metrics,
    get_recent_rides,
    get_upcoming_workouts,
    get_power_bests,
    get_training_summary,
    get_ftp_history,
    get_periodization_status,
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
)

APP_NAME = "cycling-coach"

# Singleton instances
_session_service = None
_memory_service = None
_runner = None


def _build_system_instruction(ctx) -> str:
    """Build the system instruction dynamically from database settings."""
    from server.database import get_all_settings
    settings = get_all_settings()

    return f"""You are an expert cycling coach working with a specific athlete.

ATHLETE PROFILE:
{settings['athlete_profile']}

KEY COACHING PRINCIPLES:
{settings['coaching_principles']}

YOUR ROLE:
{settings['coach_role']}

PLAN MANAGEMENT:
{settings['plan_management']}"""


def _get_agent():
    return Agent(
        name="cycling_coach",
        model=GEMINI_MODEL,
        description="Expert cycling coach",
        instruction=_build_system_instruction,
        tools=[
            get_pmc_metrics,
            get_recent_rides,
            get_upcoming_workouts,
            get_power_bests,
            get_training_summary,
            get_ftp_history,
            get_periodization_status,
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
            preload_memory_tool,
        ],
    )


def get_runner():
    global _session_service, _runner, _memory_service
    if _runner is None:
        _session_service = SqliteSessionService()
        _memory_service = SqliteMemoryService()
        _runner = Runner(
            agent=_get_agent(),
            app_name=APP_NAME,
            session_service=_session_service,
            memory_service=_memory_service,
        )
    return _runner, _session_service, _memory_service


async def chat(message: str, user_id: str = "athlete", session_id: str = "default") -> str:
    """Send a message to the coaching agent and get a response."""
    import os
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", GCP_PROJECT)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", GCP_LOCATION)
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

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
