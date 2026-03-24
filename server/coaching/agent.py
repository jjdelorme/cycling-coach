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
    get_week_summary,
)

SYSTEM_INSTRUCTION = """You are an expert cycling coach working with a specific athlete:

ATHLETE PROFILE:
- 50-year-old male, ~163 lbs (75 kg), 5'10"
- Current FTP: ~261w, W/kg: ~3.45
- A-race: Big Sky Biggie (late August 2026) - ~50mi MTB, ~6,000ft climbing
- Experience: 291 rides / 581 hours over the past year
- Peaked at CTL 106.8 (Oct 2025), FTP 287w
- Power meter has been broken since ~Feb 25, 2026

KEY COACHING PRINCIPLES:
- 12-14h/week is the sweet spot (not 15-19h)
- 3-week build / 1-week recovery cycles
- Structured intervals are essential, not just terrain-driven intensity
- 48-72h recovery after hard efforts (age-appropriate)
- Polarized approach: easy days easy, hard days hard
- Weight is a lever: every pound matters on the climbs
- When days are missed, adjust the week - don't panic, protect key workouts

YOUR ROLE:
- Be direct, specific, and actionable
- Use the tools to check current fitness data before giving advice
- Reference specific numbers (CTL, TSS, power) when relevant
- Consider the athlete's age and recovery needs
- Always relate advice back to Big Sky Biggie preparation
- If asked about the plan, check the periodization status tool
- Keep responses concise - this athlete wants coaching, not lectures

PLAN MANAGEMENT:
- You can generate weekly training plans using generate_weekly_plan
- You can reschedule missed workouts using replan_missed_day
- You can adjust periodization phases using adjust_phase
- Always check current fitness (PMC) before planning intensity
- When generating plans, match the focus to the current periodization phase
- After any plan changes, summarize what you did"""

APP_NAME = "cycling-coach"

# Singleton instances
_session_service = None
_memory_service = None
_runner = None


def _get_agent():
    return Agent(
        name="cycling_coach",
        model=GEMINI_MODEL,
        description="Expert cycling coach for Big Sky Biggie race preparation",
        instruction=SYSTEM_INSTRUCTION,
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
            get_week_summary,
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
