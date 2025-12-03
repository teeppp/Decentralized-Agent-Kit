import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)

def enforcer_validator(
    llm_response: LlmResponse, callback_context: CallbackContext
) -> Optional[LlmResponse]:
    """
    Validates that the agent response uses a tool.
    Terminal tools (attempt_answer, ask_question) will end the invocation automatically.
    """
    
    # Check if the current response has tool calls
    has_tool_call = False
    if llm_response.content and llm_response.content.parts:
        for part in llm_response.content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                has_tool_call = True
                break
    
    if has_tool_call:
        return None  # Allow responses with tool calls
    
    # Block all direct text responses - no exceptions
    # Terminal tools will end the invocation, so we never get here after them
    print("Enforcer Mode: Blocked direct text response.")
    
    error_message = """
Direct responses are not allowed in Enforcer Mode.
You must use a tool for every step.

Available Tools:
- planner: Use this FIRST to plan complex tasks.
- ask_question: Use this to ask the user for clarification.
- attempt_answer: Use this to provide the FINAL answer.
- deep_think: Use this for reasoning and analysis.
- read_file, run_command, etc.: Use these for actions.

You CANNOT just write text. You MUST call a tool.
"""
    
    # Force retry via system_retry tool
    return LlmResponse(
        content=types.Content(
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="system_retry",
                        args={"error_message": error_message}
                    )
                )
            ],
            role="model"
        )
    )
