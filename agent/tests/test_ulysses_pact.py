import pytest
from unittest.mock import MagicMock
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from dak_agent.enforcer_validator import enforcer_validator, SessionState

# Marker used by enforcer to indicate blocked response
ENFORCER_BLOCKED_MARKER = "[ENFORCER_BLOCKED]"

@pytest.fixture
def session_state():
    return SessionState()

@pytest.fixture
def mock_context():
    return MagicMock()

def create_llm_response(tool_name=None, tool_args=None, text_content=None):
    parts = []
    if text_content:
        parts.append(types.Part(text=text_content))
    
    if tool_name:
        parts.append(types.Part(
            function_call=types.FunctionCall(
                name=tool_name,
                args=tool_args or {}
            )
        ))
        
    return LlmResponse(
        content=types.Content(parts=parts, role="model")
    )

def get_text_from_response(result):
    """Helper to extract text from enforcement error response."""
    if result and result.content and result.content.parts:
        for part in result.content.parts:
            if hasattr(part, 'text') and part.text:
                return part.text
    return ""

def test_direct_text_blocked(session_state, mock_context):
    """Test that direct text without tool calls is blocked."""
    response = create_llm_response(text_content="Hello world")
    result = enforcer_validator(response, mock_context, session_state)
    
    assert result is not None
    text = get_text_from_response(result)
    assert ENFORCER_BLOCKED_MARKER in text
    assert "Direct responses are not allowed" in text

def test_planner_sets_state(session_state, mock_context):
    """Test that calling planner updates the allowed tools."""
    response = create_llm_response(
        tool_name="planner",
        tool_args={"allowed_tools": ["read_file", "run_command"]}
    )
    
    result = enforcer_validator(response, mock_context, session_state)
    
    assert result is None  # Should allow planner call
    assert session_state.active_plan is True
    assert "read_file" in session_state.allowed_tools
    assert "run_command" in session_state.allowed_tools
    assert "planner" in session_state.allowed_tools  # Default allowed

def test_allowed_tool_passes(session_state, mock_context):
    """Test that using an allowed tool passes."""
    session_state.set_plan(["read_file"])
    
    response = create_llm_response(tool_name="read_file", tool_args={"path": "test.txt"})
    result = enforcer_validator(response, mock_context, session_state)
    
    assert result is None

def test_disallowed_tool_blocked(session_state, mock_context):
    """Test that using a disallowed tool is blocked."""
    session_state.set_plan(["read_file"])
    
    response = create_llm_response(tool_name="write_file", tool_args={"path": "test.txt", "content": "x"})
    result = enforcer_validator(response, mock_context, session_state)
    
    assert result is not None
    text = get_text_from_response(result)
    assert ENFORCER_BLOCKED_MARKER in text
    assert "Violation" in text
    assert "write_file" in text

def test_no_plan_allows_any_tool(session_state, mock_context):
    """Test that without a plan, any tool is allowed (except direct text)."""
    assert session_state.active_plan is False
    
    response = create_llm_response(tool_name="random_tool", tool_args={})
    result = enforcer_validator(response, mock_context, session_state)
    
    assert result is None
