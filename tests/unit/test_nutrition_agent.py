import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from google.genai import types
from server.nutrition.agent import chat, _claims_persistence

@pytest.fixture
def mock_get_runner():
    with patch("server.nutrition.agent.get_runner") as mock:
        yield mock

@pytest.fixture
def mock_get_trace_id():
    with patch("server.nutrition.agent.get_trace_id") as mock:
        yield mock

@pytest.mark.asyncio
async def test_chat_returns_flags_clarification(mock_get_runner, mock_get_trace_id):
    """Test that chat returns requires_clarification=True when ask_clarification tool is called."""
    mock_runner = MagicMock()
    mock_session_service = AsyncMock()
    mock_memory_service = AsyncMock()
    
    mock_get_runner.return_value = (mock_runner, mock_session_service, mock_memory_service)
    
    # Synthetic event stream containing a tool call
    mock_part = MagicMock()
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "ask_clarification"
    mock_part.text = ""
    
    mock_event = MagicMock()
    mock_event.author = "nutritionist"
    mock_event.content.parts = [mock_part]
    
    # Also add a text response
    mock_text_part = MagicMock()
    mock_text_part.function_call = None
    mock_text_part.function_response = None
    mock_text_part.text = "What flavor?"
    mock_text_event = MagicMock()
    mock_text_event.author = "nutritionist"
    mock_text_event.content.parts = [mock_text_part]

    async def async_generator(*args, **kwargs):
        yield mock_event
        yield mock_text_event

    mock_runner.run_async.side_effect = async_generator
    
    response_text, requires_clarification, meal_saved = await chat(message="pop tarts", session_id="test_session")
    
    assert response_text == "What flavor?"
    assert requires_clarification is True
    assert meal_saved is False

@pytest.mark.asyncio
async def test_chat_returns_flags_saved(mock_get_runner, mock_get_trace_id):
    """Test that chat returns meal_saved=True when save_meal_analysis tool is called."""
    mock_runner = MagicMock()
    mock_session_service = AsyncMock()
    mock_memory_service = AsyncMock()
    
    mock_get_runner.return_value = (mock_runner, mock_session_service, mock_memory_service)
    
    mock_part = MagicMock()
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "save_meal_analysis"
    mock_part.text = ""
    
    mock_event = MagicMock()
    mock_event.author = "nutritionist"
    mock_event.content.parts = [mock_part]
    
    mock_text_part = MagicMock()
    mock_text_part.function_call = None
    mock_text_part.function_response = None
    mock_text_part.text = "Meal saved!"
    mock_text_event = MagicMock()
    mock_text_event.author = "nutritionist"
    mock_text_event.content.parts = [mock_text_part]

    async def async_generator(*args, **kwargs):
        yield mock_event
        yield mock_text_event

    mock_runner.run_async.side_effect = async_generator
    
    response_text, requires_clarification, meal_saved = await chat(message="chicken", session_id="test_session")

    assert response_text == "Meal saved!"
    assert requires_clarification is False
    assert meal_saved is True


# ---------------------------------------------------------------------------
# Hallucinated-persistence guard
# ---------------------------------------------------------------------------

class TestClaimsPersistenceRegex:
    """The heuristic must catch agent claims of having saved a plan/meal
    while ignoring benign phrasing like 'would be saved' or 'you can save'."""

    @pytest.mark.parametrize("text", [
        "I have persisted this plan to your dashboard.",
        "I have saved your meal plan for next week.",
        "I added breakfast and lunch to your plan.",
        "Your plan has been saved.",
        "I created a 7-day meal plan and pushed it to your dashboard.",
        "I have logged the meal.",
        "The meal plan has been added to your dashboard.",
        "I've updated your meal plan.",
    ])
    def test_positive_claims_are_detected(self, text):
        assert _claims_persistence(text), f"Should detect: {text!r}"

    @pytest.mark.parametrize("text", [
        "Here is a suggested plan. Would you like me to save it?",
        "You can save this as a breakfast template.",
        "A typical plan for a heavy day would include extra carbs.",
        "This would be saved as breakfast slot.",
        "Your dashboard shows three meals already planned.",
        "I checked your training load and dietary preferences.",
        "I recommend an oatmeal breakfast.",
        "Your CTL has been trending up.",
        "",
    ])
    def test_benign_phrasing_does_not_fire(self, text):
        assert not _claims_persistence(text), f"Should NOT fire on: {text!r}"


def _make_event(*, fn_name=None, text=None, author="nutritionist"):
    """Build a synthetic ADK event with a function_call OR text part."""
    part = MagicMock()
    if fn_name is not None:
        part.function_call = MagicMock()
        part.function_call.name = fn_name
        part.function_response = None
        part.text = ""
    else:
        part.function_call = None
        part.function_response = None
        part.text = text or ""
    event = MagicMock()
    event.author = author
    event.content.parts = [part]
    return event


def _runner_yielding(events):
    """Build a runner mock whose run_async yields the given events."""
    async def gen(*args, **kwargs):
        for e in events:
            yield e
    runner = MagicMock()
    runner.run_async.side_effect = gen
    return runner


@pytest.mark.asyncio
async def test_chat_overrides_response_when_no_write_tool_called(
    mock_get_runner, mock_get_trace_id,
):
    """Agent claims 'persisted to dashboard' but only called read tools.
    The user-facing response must be replaced and a warning logged."""
    runner = _runner_yielding([
        _make_event(fn_name="get_planned_meals"),
        _make_event(text="I have persisted this plan to your dashboard."),
    ])
    mock_get_runner.return_value = (runner, AsyncMock(), AsyncMock())

    with patch("server.nutrition.agent.logger") as mock_logger:
        response, _, _ = await chat(message="plan my week", session_id="s1")

    assert "did not actually save" in response.lower()
    assert "persisted this plan" not in response  # original claim is gone
    mock_logger.warning.assert_called_once()
    assert mock_logger.warning.call_args.args[0] == "nutritionist_hallucinated_persistence"


@pytest.mark.asyncio
async def test_chat_keeps_response_when_write_tool_was_called(
    mock_get_runner, mock_get_trace_id,
):
    """When generate_meal_plan WAS called, the persistence claim is real
    and must be left intact."""
    runner = _runner_yielding([
        _make_event(fn_name="generate_meal_plan"),
        _make_event(text="I have saved your plan to the dashboard."),
    ])
    mock_get_runner.return_value = (runner, AsyncMock(), AsyncMock())

    with patch("server.nutrition.agent.logger") as mock_logger:
        response, _, _ = await chat(message="plan my week", session_id="s2")

    assert response == "I have saved your plan to the dashboard."
    # Hallucination warning must NOT fire when the write tool ran
    warning_calls = [c for c in mock_logger.warning.call_args_list
                     if c.args and c.args[0] == "nutritionist_hallucinated_persistence"]
    assert warning_calls == []


@pytest.mark.asyncio
async def test_chat_keeps_response_when_no_persistence_claim(
    mock_get_runner, mock_get_trace_id,
):
    """No write tool called and no persistence claim -- guard stays silent."""
    runner = _runner_yielding([
        _make_event(fn_name="get_meal_history"),
        _make_event(text="Your last 3 meals averaged 600 kcal each."),
    ])
    mock_get_runner.return_value = (runner, AsyncMock(), AsyncMock())

    with patch("server.nutrition.agent.logger") as mock_logger:
        response, _, _ = await chat(message="how am i eating?", session_id="s3")

    assert response == "Your last 3 meals averaged 600 kcal each."
    warning_calls = [c for c in mock_logger.warning.call_args_list
                     if c.args and c.args[0] == "nutritionist_hallucinated_persistence"]
    assert warning_calls == []

