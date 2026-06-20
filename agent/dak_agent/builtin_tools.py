"""Built-in agent control tools.

These tools are always available and are never removed by mode switching
or skill filtering.
"""
from typing import List

from google.adk.tools import FunctionTool


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
    plan_str = "\n".join([f"{i + 1}. {step}" for i, step in enumerate(plan_steps)])

    restriction_msg = ""
    if allowed_tools:
        restriction_msg = (
            f"\n\n[System] Ulysses Pact Active: You are now restricted to using only: "
            f"{', '.join(allowed_tools)}"
        )

    return f"Plan recorded for '{task_description}':\n{plan_str}{restriction_msg}"


def switch_mode(reason: str = "", new_focus: str = "") -> str:
    """
    Request a mode switch.

    Args:
        reason: Why you want to switch modes (e.g., "Need to use File System tools").
        new_focus: What the new mode should focus on (e.g., "File Operations").

    Workflow:
    1. If you don't know what tools are available, call `list_skills` first.
    2. Call `switch_mode(reason="...", new_focus="...")` to switch to a mode that includes the desired tools.
    """
    return f"Mode switch requested: {reason}. New focus: {new_focus}"


def make_builtin_tools(enforcer_mode: bool = False) -> List[FunctionTool]:
    """Create the built-in control tools for the root agent.

    `attempt_answer` / `ask_question` are only useful in Enforcer Mode, where
    free-text responses are blocked.
    """
    tools = [
        FunctionTool(planner, require_confirmation=True),
        FunctionTool(switch_mode, require_confirmation=False),
    ]
    if enforcer_mode:
        tools.append(FunctionTool(attempt_answer, require_confirmation=False))
        tools.append(FunctionTool(ask_question, require_confirmation=False))
    return tools
