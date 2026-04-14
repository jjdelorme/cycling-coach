"""Test AgentTool availability and wiring."""


def test_agent_tool_import():
    """AgentTool can be imported from google.adk.tools."""
    from google.adk.tools import AgentTool

    assert AgentTool is not None


def test_agent_tool_import_from_module():
    """AgentTool can be imported from the agent_tool module directly."""
    from google.adk.tools.agent_tool import AgentTool

    assert AgentTool is not None


def test_nutritionist_agent_getter():
    """get_nutritionist_agent returns an Agent instance."""
    from server.nutrition.agent import get_nutritionist_agent

    agent = get_nutritionist_agent()
    assert agent.name == "nutritionist"
    assert agent.description is not None
    assert len(agent.description) > 0


def test_agent_tool_wraps_nutritionist():
    """AgentTool wraps the nutritionist agent correctly."""
    from google.adk.tools import AgentTool
    from server.nutrition.agent import get_nutritionist_agent

    tool = AgentTool(agent=get_nutritionist_agent())
    assert tool.name == "nutritionist"


def test_nutritionist_agent_has_tools():
    """Nutritionist agent has expected tools configured."""
    from server.nutrition.agent import get_nutritionist_agent

    agent = get_nutritionist_agent()
    tool_names = [
        t.__name__ if hasattr(t, "__name__") else str(t) for t in agent.tools
    ]
    # Should include read tools (unwrapped) and write tools (wrapped)
    assert "get_meal_history" in tool_names
    assert "get_daily_macros" in tool_names
    assert "get_caloric_balance" in tool_names
    assert "ask_clarification" in tool_names


def test_coach_agent_includes_nutritionist_tool():
    """Coach agent tools list includes the nutritionist AgentTool."""
    from google.adk.tools.agent_tool import AgentTool
    from server.coaching.agent import _get_agent

    agent = _get_agent()
    agent_tools = [t for t in agent.tools if isinstance(t, AgentTool)]
    assert len(agent_tools) == 1
    assert agent_tools[0].name == "nutritionist"


def test_coach_system_prompt_includes_nutrition_section():
    """Coach system prompt includes nutrition integration guidance."""
    from server.coaching.agent import _build_system_instruction

    # _build_system_instruction takes a context arg (can be None for testing)
    prompt = _build_system_instruction(None)
    assert "NUTRITION INTEGRATION:" in prompt
    assert "QUICK CHECK" in prompt
    assert "COMPLEX FUELING GUIDANCE" in prompt
    assert "NUTRITION-AWARE COACH NOTES:" in prompt
    assert "get_athlete_nutrition_status" in prompt


def test_nutritionist_chat_accepts_audio_params():
    """chat() function signature accepts audio_data and audio_mime_type."""
    import inspect
    from server.nutrition.agent import chat

    sig = inspect.signature(chat)
    params = list(sig.parameters.keys())
    assert "audio_data" in params
    assert "audio_mime_type" in params
