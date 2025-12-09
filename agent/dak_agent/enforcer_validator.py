import logging
from typing import Optional, Set, List

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)

class SessionState:
    """
    Tracks the current session state for the Ulysses Pact pattern.
    """
    def __init__(self):
        self.active_plan: bool = False
        self.allowed_tools: Set[str] = set()

    def set_plan(self, tools: List[str]):
        self.active_plan = True
        # Always allow these core tools
        defaults = {"planner", "ask_question", "attempt_answer", "deep_think", "system_retry", "switch_mode"}
        self.allowed_tools = set(tools) | defaults
        print(f"[Enforcer] Plan set! Allowed tools: {self.allowed_tools}")

    def clear_plan(self):
        self.active_plan = False
        self.allowed_tools = set()
        print("[Enforcer] Plan cleared.")

def enforcer_validator(
    llm_response: LlmResponse, 
    callback_context: CallbackContext,
    session_state: SessionState
) -> Optional[LlmResponse]:
    """
    Validates that the agent response follows the Ulysses Pact.
    1. Checks if 'planner' is called to update the pact.
    2. If a pact is active, enforces that only allowed tools are used.
    3. Blocks direct text responses (unless asking question or answering).
    """
    
    # Check for tool calls
    tool_calls = []
    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                tool_calls.append(part.function_call)
    
    has_tool_call = len(tool_calls) > 0
    
    # 1. Block direct text responses if no tool is called
    if not has_tool_call:
        print("Enforcer Mode: Blocked direct text response.")
        error_message = """
Direct responses are not allowed in Enforcer Mode.
You must use a tool for every step.

Available Tools:
- planner: Use this to plan and set your allowed tools (Ulysses Pact).
- ask_question: Use this to ask the user for clarification.
- attempt_answer: Use this to provide the FINAL answer.
- other tools: As defined in your plan.

You CANNOT just write text. You MUST call a tool.

If you are missing tools to fulfill the request:
1. Call `switch_mode(request_tool_list=True)` to find available tools.
2. Then call `switch_mode` again to switch.
"""
        return _create_enforcement_error(error_message)

    # 2. Process tool calls
    for tool_call in tool_calls:
        tool_name = tool_call.name
        
        # Check if planner is called to update state
        if tool_name == "planner":
            args = tool_call.args
            allowed_tools = args.get("allowed_tools", [])
            # Handle case where allowed_tools might be None or not present
            if allowed_tools:
                # If it's a list, use it. If it's a string (unlikely but possible from LLM), wrap it.
                if isinstance(allowed_tools, str):
                    allowed_tools = [allowed_tools]
                session_state.set_plan(list(allowed_tools))
            continue

        # 3. Enforce Ulysses Pact if active
        if session_state.active_plan:
            if tool_name not in session_state.allowed_tools:
                print(f"Enforcer Mode: Blocked tool '{tool_name}' (not in plan).")
                error_message = f"""
🚫 Violation: Tool '{tool_name}' is not in your active plan.
Allowed tools: {list(session_state.allowed_tools)}

Action:
1. Use an allowed tool.
2. OR call 'planner' again to update your plan and allowed tools.
"""
                return _create_enforcement_error(error_message)

    return None  # Allow response

class EnforcerBlockedError(Exception):
    """Exception raised when enforcer blocks a response."""
    pass

def _create_enforcement_error(error_message: str) -> LlmResponse:
    """
    Creates a text-based enforcement error response.
    
    This approach works with all Gemini models including Gemini 3 Pro,
    which requires thought_signature for function calls. By using text
    instead of a function call, we avoid this API limitation.
    
    The [ENFORCER_BLOCKED] marker allows clients (CLI/UI) to detect
    these errors and automatically retry.
    """
    formatted_message = f"""[ENFORCER_BLOCKED]
{error_message}

---
[This response was blocked by Enforcer Mode. The model must use a tool to proceed.]
"""
    # Return the error response - this ends the current turn
    # The client CLI will detect [ENFORCER_BLOCKED] and handle retry
    return LlmResponse(
        content=types.Content(
            parts=[
                types.Part(text=formatted_message)
            ],
            role="model"
        ),
        # Signal that we want to stop processing
        turn_complete=True
    )
