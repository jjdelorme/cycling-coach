import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from google.genai import types
from server.nutrition.agent import chat

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

