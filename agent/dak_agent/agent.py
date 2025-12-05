from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from .enforcer_validator import enforcer_validator
import os
# Langfuse OpenTelemetry Instrumentation
try:
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    from langfuse import get_client
    
    # Instrument Google ADK for OpenTelemetry tracing
    GoogleADKInstrumentor().instrument()
    
    # Optional: Verify Langfuse authentication if environment variables are set
    if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
        try:
            langfuse = get_client()
            if langfuse.auth_check():
                print("[Langfuse] Authentication successful - monitoring enabled")
                from openinference.instrumentation.google_adk import GoogleADKInstrumentor
                GoogleADKInstrumentor().instrument()
            else:
                print("[Langfuse] Authentication failed - check your credentials")
        except Exception as e:
            print(f"[Langfuse] Connection error: {e}")
except Exception as e:
    # Silently skip if Langfuse dependencies are not installed or incompatible
    print(f"[Langfuse] Skipping instrumentation: {type(e).__name__}")
    pass

# MCP Server configuration
mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")

from pydantic import ConfigDict

class PatchedMcpToolset(McpToolset):
    model_config = ConfigDict(arbitrary_types_allowed=True)

# Create MCP toolset
mcp_toolset = PatchedMcpToolset(
    connection_params=StreamableHTTPConnectionParams(url=mcp_url),
    require_confirmation=True
)

from google.adk.tools import FunctionTool

# =====================================
# BUILT-IN CONTROL TOOLS
# These are agent control tools that should NEVER be filtered
# =====================================

def system_retry(error_message: str) -> str:
    """
    INTERNAL TOOL. Do not use this tool directly.
    Used by the system to force a retry when an error occurs.
    """
    print(f"SYSTEM RETRY TRIGGERED: {error_message[:50]}...")
    return f"""SYSTEM ERROR - RETRY REQUIRED:
{error_message}

NEXT ACTION REQUIRED: You MUST call one of these tools NOW:
- `planner` if you need to plan
- `ask_question` if you need user input
- `attempt_answer` if you have the final answer
- Other tools for specific actions

DO NOT respond with text. CALL A TOOL."""

def attempt_answer(answer: str, confidence: str, sources_used: list[str], tool_context) -> str:
    """
    Provide a final answer to the user.
    Args:
        answer: The final answer to provide.
        confidence: Confidence level (e.g., "high", "medium", "low").
        sources_used: List of sources or tools used to derive the answer.
    """
    # End the invocation after providing the answer
    tool_context._invocation_context.end_invocation = True
    
    sources_str = ""
    if sources_used:
        sources_str = f"\n\nSources: {', '.join(sources_used)}"
    
    return f"Answer (Confidence: {confidence}):\n{answer}{sources_str}"

def ask_question(questions: list[str], context: str, tool_context) -> str:
    """
    Ask clarifying questions to the user.
    Args:
        questions: List of questions to ask.
        context: Why these questions are needed.
    """
    # End the invocation after asking questions  
    tool_context._invocation_context.end_invocation = True
    
    questions_str = "\n".join([f"- {q}" for q in questions])
    return f"Context: {context}\n\nQuestions for user:\n{questions_str}\n\n(Waiting for user response...)"

def planner(task_description: str, plan_steps: list[str], allowed_tools: list[str] = []) -> str:
    """
    Create a plan and restrict future actions to specific tools (Ulysses Pact).
    Args:
        task_description: Description of the task to plan for.
        plan_steps: Ordered list of steps to accomplish the task.
        allowed_tools: List of tool names you intend to use (e.g. ["read_file", "run_command"]).
                       'planner', 'ask_question', 'attempt_answer', 'switch_mode' are always allowed.
    """
    plan_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(plan_steps)])
    
    restriction_msg = ""
    if allowed_tools:
        restriction_msg = f"\n\n[System] Ulysses Pact Active: You are now restricted to using only: {', '.join(allowed_tools)}"
    
    return f"Plan recorded for '{task_description}':\n{plan_str}{restriction_msg}"

def switch_mode(reason: str, new_focus: str) -> str:
    """
    Request a mode switch when you feel the conversation has shifted
    or the context is becoming too heavy.
    
    Args:
        reason: Why you want to switch modes (e.g., "Context is heavy", "New phase started")
        new_focus: What the new mode should focus on
    
    This tool triggers the Mode Manager to create a new, focused configuration.
    """
    return f"Mode switch requested: {reason}. New focus: {new_focus}"

# Create FunctionTool instances
system_retry_tool = FunctionTool(system_retry, require_confirmation=False)
attempt_answer_tool = FunctionTool(attempt_answer, require_confirmation=False)
ask_question_tool = FunctionTool(ask_question, require_confirmation=False)
planner_tool = FunctionTool(planner, require_confirmation=False)
switch_mode_tool = FunctionTool(switch_mode, require_confirmation=False)

# Define the root agent
after_model_callback = None
instruction = 'You are a helpful assistant powered by the Decentralized Agent Kit.'

# Built-in control tools that are ALWAYS available (never filtered)
# These are added separately from mcp_toolset so they survive mode switching
root_agent_tools = [mcp_toolset, planner_tool, switch_mode_tool]

if os.getenv("ENABLE_ENFORCER_MODE", "false").lower() == "true":
    from .enforcer_validator import SessionState
    
    # Instantiate session state for Ulysses Pact
    session_state = SessionState()
    
    # Create a closure to pass session_state to the validator
    after_model_callback = lambda llm_response, callback_context: enforcer_validator(llm_response, callback_context, session_state)
    
    instruction = '''You are a helpful assistant powered by the Decentralized Agent Kit.

IMPORTANT: You are in ENFORCER MODE. You MUST use a tool for EVERY response. Direct text responses are NOT allowed.

# Ulysses Pact (Self-Correction)
You have the ability to bind yourself to a specific plan using the `planner` tool.
1. **Complex Tasks**: If a task requires multiple steps, call `planner` with `allowed_tools` list.
   - This creates a "Ulysses Pact" where the system will BLOCK any tool not in your plan.
   - This helps you stay focused and avoid hallucinations or off-track actions.
2. **Simple Tasks**: You can proceed without planning if the task is simple.

# Workflow
1. Analyze the request. Is it complex?
   - YES: Call `planner(..., allowed_tools=["tool_a", "tool_b"])`.
   - NO: Call the appropriate tool directly.
2. If you get a "Violation" error, it means you tried to use a tool not in your plan.
   - Fix: Use an allowed tool OR call `planner` again to update your plan.
3. **Context Management**: If you feel the conversation is getting too long or you are shifting to a completely new phase of the task:
   - Call `switch_mode(reason="...", new_focus="...")`.
   - This will refresh your context and tools for the new phase.

You can ONLY output text AFTER calling `ask_question` or `attempt_answer`. Otherwise you MUST call a tool.'''
    # Add Enforcer-specific tools only in Enforcer Mode
    root_agent_tools.extend([system_retry_tool, attempt_answer_tool, ask_question_tool])

from .adaptive_agent import AdaptiveAgent

# Define the root agent
# We wrap the standard LlmAgent with our AdaptiveAgent to enable dynamic mode switching
root_agent = AdaptiveAgent(
    model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
    name='dak_agent',
    instruction=instruction,
    tools=root_agent_tools,
    after_model_callback=after_model_callback
)
