"""Built-in agent control tools.

These tools are always available and are never removed by mode switching
or skill filtering.
"""
import json
import os
from typing import List

from google.adk.tools import FunctionTool

# Session-state key holding the agent's plan: [{"step": str, "status": str}].
# Kept in state (not in the event history), so context compaction never
# summarises it away.
STATE_TODOS = "dak_todos"
TODO_STATUSES = ("pending", "in_progress", "done")


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
                       'planner', 'ask_question', 'attempt_answer', 'switch_mode', 'write_todos' and
                       'read_plan' are always allowed.
    """
    plan_str = "\n".join([f"{i + 1}. {step}" for i, step in enumerate(plan_steps)])

    restriction_msg = ""
    if allowed_tools:
        restriction_msg = (
            f"\n\n[System] Ulysses Pact Active: You are now restricted to using only: "
            f"{', '.join(allowed_tools)}"
        )

    return f"Plan recorded for '{task_description}':\n{plan_str}{restriction_msg}"


def _normalize_status(status) -> str:
    s = str(status or "").strip().lower().replace(" ", "_").replace("-", "_")
    s = {"completed": "done", "complete": "done", "inprogress": "in_progress"}.get(s, s)
    return s if s in TODO_STATUSES else "pending"


def _normalize_item(item) -> dict:
    if not isinstance(item, dict):
        return {"step": str(item), "status": "pending"}
    return {"step": str(item.get("step", "")), "status": _normalize_status(item.get("status"))}


def format_todos(items: list) -> str:
    """One numbered line per plan item: `1. [done] read repo`. Tolerates plan
    state not written by write_todos (a client may seed it)."""
    lines = []
    for i, item in enumerate(items):
        item = _normalize_item(item)
        lines.append(f"{i + 1}. [{item['status']}] {item['step']}")
    return "\n".join(lines)


def write_todos(items: list[dict], tool_context) -> str:
    """
    Record (or replace) your plan and the progress of each step. Call it again
    whenever a step's status changes. The plan stays available after the
    conversation history is compacted.
    Args:
        items: The whole plan, in order, as a list. Each item is {"step": "...", "status": "pending" | "in_progress" | "done"}.
    """
    if isinstance(items, str):
        # Small models often send a nested array as a JSON string.
        try:
            items = json.loads(items)
        except ValueError:
            pass
    if not isinstance(items, list):
        # Never overwrite the saved plan with something that is not a plan.
        return ('Error: items must be a list like [{"step": "...", "status": "pending"}]; '
                "the saved plan was not changed.")
    todos = [_normalize_item(item) for item in items]
    tool_context.state[STATE_TODOS] = todos
    return f"Plan saved:\n{format_todos(todos)}"


def read_plan(tool_context) -> str:
    """
    Read your current plan and the progress of each step (as saved by write_todos).
    """
    todos = tool_context.state.get(STATE_TODOS) or []
    return format_todos(todos) if isinstance(todos, list) and todos else "No plan recorded yet."


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


def planner_requires_confirmation() -> bool:
    """Whether `planner` pauses for human approval (opt-in).

    `planner` has no side effects: it records a plan and *narrows* the agent's
    own future tool set (Ulysses Pact). Requiring confirmation therefore buys
    no safety, and it stalls every client that cannot answer a confirmation
    request mid-run (`/run`, A2A, CLI), where planning is the agent's first
    step. Set DAK_PLANNER_REQUIRE_CONFIRMATION=true to get the old behaviour.
    """
    return os.getenv("DAK_PLANNER_REQUIRE_CONFIRMATION", "false").lower() == "true"


def make_builtin_tools(enforcer_mode: bool = False) -> List[FunctionTool]:
    """Create the built-in control tools for the root agent.

    `attempt_answer` / `ask_question` are only useful in Enforcer Mode, where
    free-text responses are blocked.
    """
    tools = [
        FunctionTool(planner, require_confirmation=planner_requires_confirmation()),
        FunctionTool(switch_mode, require_confirmation=False),
        FunctionTool(write_todos, require_confirmation=False),
        FunctionTool(read_plan, require_confirmation=False),
    ]
    if enforcer_mode:
        tools.append(FunctionTool(attempt_answer, require_confirmation=False))
        tools.append(FunctionTool(ask_question, require_confirmation=False))
    return tools
