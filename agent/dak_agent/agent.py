from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from .enforcer_validator import enforcer_validator
import os

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

# Define system_retry tool locally to avoid confirmation
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

# Define terminal tools that end the agent loop
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

from google.adk.tools import FunctionTool
system_retry_tool = FunctionTool(system_retry, require_confirmation=False)
attempt_answer_tool = FunctionTool(attempt_answer, require_confirmation=False)
ask_question_tool = FunctionTool(ask_question, require_confirmation=False)

# Define the root agent
after_model_callback = None
instruction = 'You are a helpful assistant powered by the Decentralized Agent Kit.'

root_agent_tools = [mcp_toolset]
if os.getenv("ENABLE_ENFORCER_MODE", "false").lower() == "true":
    after_model_callback = enforcer_validator
    instruction = '''You are a helpful assistant powered by the Decentralized Agent Kit.

IMPORTANT: You are in ENFORCER MODE. You MUST use a tool for EVERY response. Direct text responses are NOT allowed.

Workflow:
1. For complex tasks: Use `planner` tool first
2. For clarification: Use `ask_question` tool
3. For final answers: Use `attempt_answer` tool
4. For other actions: Use appropriate tools (read_file, run_command, etc.)

You can ONLY output text AFTER calling `ask_question` or `attempt_answer`. Otherwise you MUST call a tool.'''
    # Add Enforcer-specific tools only in Enforcer Mode
    root_agent_tools.extend([system_retry_tool, attempt_answer_tool, ask_question_tool])

root_agent = LlmAgent(
    # model='gemini-3-pro-preview',
    model='gemini-2.5-flash',
    name='dak_agent',
    instruction=instruction,
    tools=root_agent_tools,
    after_model_callback=after_model_callback
)
