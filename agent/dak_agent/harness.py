"""Context-engineering harness: keep every model request inside the context window.

Three layers, cheapest first:

1. Tool-output budget (``ContextHarnessPlugin.after_tool_callback``): an
   oversized tool result is replaced by a head/tail preview and the full text
   is offloaded to an artifact the agent can page through with
   ``read_tool_output`` (the "evict large tool results" pattern of Deep Agents).
2. ADK token-threshold compaction (``EventsCompactionConfig``): before each
   model call ADK summarizes older session events once the last observed prompt
   crossed ``token_threshold`` - this works *within* a single long invocation.
3. Request guard (``ContextHarnessPlugin.before_model_callback``): keeps a
   user turn in the request after compaction (chat templates require one) and,
   as a last resort, elides the oldest tool payloads when the assembled request
   would still overflow (e.g. the summarizer failed).

All limits derive from the model's context window (``MODEL_CONTEXT_WINDOW`` or
LiteLLM's model map), so a llama.cpp server launched with 8K gets tight budgets
while a 1M-token Gemini model is left mostly alone.
"""
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from google.adk.apps.app import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import FunctionTool
from google.genai import types

from .mode_manager import ModeManager

logger = logging.getLogger(__name__)

READ_TOOL_OUTPUT_NAME = "read_tool_output"

# Fraction of the context window a single tool result may occupy. Several
# results usually accumulate before compaction can run, so keep it small.
_TOOL_OUTPUT_WINDOW_FRACTION = 0.15
_MIN_TOOL_OUTPUT_CHARS = 2_000
_MAX_TOOL_OUTPUT_CHARS = 40_000

_ELIDED_TEMPLATE = (
    "[elided {chars} chars to fit the context window; call the tool again "
    "(or read_tool_output) if you still need this data]"
)

COMPACTION_PROMPT_TEMPLATE = (
    "You are compacting the working memory of an AI agent that is in the middle "
    "of a task. The raw history below will be replaced by your summary, so keep "
    "everything the agent needs to continue without redoing work.\n"
    "Write the summary with these sections:\n"
    "1. User request: restate the user's original request verbatim, plus any "
    "later corrections.\n"
    "2. Progress: what has been done, which files/tools/sources were already "
    "examined, and the key facts or findings obtained (keep exact paths, names, "
    "numbers and identifiers).\n"
    "3. Decisions: choices made and why.\n"
    "4. Remaining work: open questions and the next concrete steps.\n"
    "Be concise; drop raw tool output once its findings are captured. Output "
    "only the summary itself, with no preamble.\n\n"
    "{conversation_history}"
)


def estimate_tokens(text: str) -> int:
    """Conservative token estimate.

    ~4 ASCII chars per token for code/English, but CJK text is closer to one
    token per character; a plain ``len // 4`` underestimates Japanese prompts
    by 3-4x, which is exactly how an 8K local model overflows.
    """
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return ascii_chars // 4 + (len(text) - ascii_chars)


def _env_float(name: str, default: float, low: float, high: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        if not low < value <= high:
            raise ValueError
        return value
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s.", name, raw, default)
        return default


def _env_int(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value < minimum:
            raise ValueError
        return value
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s.", name, raw, default)
        return default


@dataclass(frozen=True)
class HarnessSettings:
    """Context budgets, all derived from the model's context window."""

    context_window: int
    compaction_threshold_ratio: float = 0.6
    compaction_retain_events: int = 4
    compaction_interval: int = 20
    request_budget_ratio: float = 0.85
    tool_output_max_chars: Optional[int] = None

    @classmethod
    def from_env(cls, model_name: str) -> "HarnessSettings":
        return cls(
            context_window=ModeManager.resolve_context_window(model_name),
            compaction_threshold_ratio=_env_float("DAK_COMPACTION_THRESHOLD_RATIO", 0.6, 0.0, 1.0),
            compaction_retain_events=_env_int("DAK_COMPACTION_RETAIN_EVENTS", 4, 0),
            compaction_interval=_env_int("DAK_COMPACTION_INTERVAL", 20, 1),
            request_budget_ratio=_env_float("DAK_REQUEST_BUDGET_RATIO", 0.85, 0.0, 1.0),
            tool_output_max_chars=_env_int("DAK_TOOL_OUTPUT_MAX_CHARS", 0, 0) or None,
        )

    @property
    def compaction_token_threshold(self) -> int:
        return max(1, int(self.context_window * self.compaction_threshold_ratio))

    @property
    def request_token_budget(self) -> int:
        return max(1, int(self.context_window * self.request_budget_ratio))

    @property
    def tool_output_chars(self) -> int:
        if self.tool_output_max_chars:
            return self.tool_output_max_chars
        # Budget in tokens -> chars, pessimistically at ~1 char/token so that
        # CJK output also fits.
        budget = int(self.context_window * _TOOL_OUTPUT_WINDOW_FRACTION)
        return max(_MIN_TOOL_OUTPUT_CHARS, min(_MAX_TOOL_OUTPUT_CHARS, budget))


def harness_enabled() -> bool:
    return os.getenv("DAK_CONTEXT_HARNESS", "true").lower() != "false"


def make_compaction_config(settings: HarnessSettings, llm: Any = None) -> EventsCompactionConfig:
    """ADK events compaction: token-threshold (in-invocation) + sliding window.

    ``llm`` is the summarizer model; without it ADK falls back to the root
    agent's model with its generic prompt.
    """
    summarizer = (
        LlmEventSummarizer(llm=llm, prompt_template=COMPACTION_PROMPT_TEMPLATE) if llm is not None else None
    )
    return EventsCompactionConfig(
        summarizer=summarizer,
        token_threshold=settings.compaction_token_threshold,
        event_retention_size=settings.compaction_retain_events,
        compaction_interval=settings.compaction_interval,
        overlap_size=1,
    )


# --- Tool-output budget ---


def _result_text(result: Any) -> Optional[str]:
    """Flatten a tool result to the text the model would see.

    Returns None for results we must not rewrite (e.g. MCP media content).
    """
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            if not all(isinstance(item, dict) and item.get("type") == "text" for item in content):
                return None
            return "\n".join(item.get("text", "") for item in content)
        if set(result) == {"result"} and isinstance(result["result"], str):
            return result["result"]
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def _drop_duplicate_structured_content(result: Any, text: str) -> Optional[dict]:
    """FastMCP mirrors a str return value into ``structuredContent.result``, so
    the model would read every MCP result twice. Drop the mirror (None if the
    result is not such a duplicate)."""
    if not isinstance(result, dict):
        return None
    structured = result.get("structuredContent")
    if not isinstance(structured, dict) or list(structured.values()) != [text]:
        return None
    return {k: v for k, v in result.items() if k != "structuredContent"}


def _preview(text: str, max_chars: int) -> str:
    head = int(max_chars * 0.7)
    tail = max_chars - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n\n... [{omitted} chars omitted] ...\n\n{text[-tail:]}"


def _artifact_name(tool_name: str, call_id: Optional[str]) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{tool_name}_{call_id or 'call'}")
    return f"tool_output_{safe}.txt"


def make_read_tool_output_tool(max_chars: int) -> FunctionTool:
    """Paging tool for results offloaded by the tool-output budget."""

    async def read_tool_output(
        artifact_name: str,
        offset: int = 0,
        limit: int = 0,
        pattern: str = "",
        tool_context=None,
    ) -> dict:
        """
        Read part of a tool result that was too large to return in full.

        Args:
            artifact_name: The `full_output_artifact` value from a truncated tool result.
            offset: Character offset to start reading from.
            limit: Maximum characters to return (0 = the largest allowed page).
            pattern: Optional regular expression; if set, return only matching lines
                     (with line numbers) instead of a character range.
        """
        part = await tool_context.load_artifact(artifact_name)
        if part is None:
            return {"error": f"Artifact '{artifact_name}' not found."}
        text = part.text
        if text is None and part.inline_data and part.inline_data.data:
            text = part.inline_data.data.decode("utf-8", errors="replace")
        text = text or ""

        page = max_chars if limit <= 0 else min(limit, max_chars)
        if pattern:
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return {"error": f"Invalid pattern: {e}"}
            matches = [f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1) if regex.search(line)]
            joined = "\n".join(matches)
            return {
                "matches": joined[:page],
                "match_count": len(matches),
                "truncated": len(joined) > page,
            }

        offset = max(0, offset)
        chunk = text[offset : offset + page]
        next_offset = offset + len(chunk)
        return {
            "content": chunk,
            "offset": offset,
            "next_offset": next_offset,
            "total_chars": len(text),
            "done": next_offset >= len(text),
        }

    return FunctionTool(read_tool_output, require_confirmation=False)


# --- Request budget guard ---


def _part_tokens(part: types.Part) -> int:
    total = 0
    if part.text:
        total += estimate_tokens(part.text)
    if part.function_call:
        total += estimate_tokens(json.dumps(part.function_call.args or {}, ensure_ascii=False, default=str))
    if part.function_response:
        total += estimate_tokens(json.dumps(part.function_response.response or {}, ensure_ascii=False, default=str))
    return total


def _content_tokens(content: types.Content) -> int:
    return sum(_part_tokens(p) for p in content.parts or [])


def _fixed_request_tokens(llm_request) -> int:
    """System instruction + tool declarations: present in every request, not trimmable."""
    config = llm_request.config
    if config is None:
        return 0
    total = 0
    si = config.system_instruction
    if isinstance(si, str):
        total += estimate_tokens(si)
    elif si is not None:
        try:
            total += estimate_tokens(si.model_dump_json(exclude_none=True))
        except Exception:
            total += estimate_tokens(str(si))
    for tool in config.tools or []:
        try:
            total += estimate_tokens(tool.model_dump_json(exclude_none=True))
        except Exception:
            total += estimate_tokens(str(tool))
    return total


def _elide_part(part: types.Part, kind: str) -> Optional[types.Part]:
    """Return a slimmed copy of `part` for `kind`, or None if nothing to remove."""
    if kind == "function_response" and part.function_response:
        response = part.function_response.response or {}
        size = len(json.dumps(response, ensure_ascii=False, default=str))
        if size <= 200:
            return None
        return types.Part(
            function_response=types.FunctionResponse(
                id=part.function_response.id,
                name=part.function_response.name,
                response={"result": _ELIDED_TEMPLATE.format(chars=size)},
            )
        )
    if kind == "text" and part.text and not part.thought and len(part.text) > 1_000:
        return types.Part(text=part.text[:500] + "\n" + _ELIDED_TEMPLATE.format(chars=len(part.text) - 500))
    return None


def fit_request_to_budget(llm_request, budget_tokens: int, keep_last: int = 2) -> int:
    """Elide the oldest tool payloads / long texts until the request fits.

    Contents are replaced, never mutated in place: ADK builds the request from
    the session's own Content objects, so in-place edits would corrupt history.
    The newest `keep_last` contents (the turn being answered) are untouched.
    Returns the number of parts elided.
    """
    contents = llm_request.contents or []
    fixed = _fixed_request_tokens(llm_request)
    total = fixed + sum(_content_tokens(c) for c in contents)
    if total <= budget_tokens:
        return 0

    elided = 0
    # Two passes: tool responses first (bulky, re-fetchable), then long texts.
    for kind in ("function_response", "text"):
        for index in range(max(0, len(contents) - keep_last)):
            if total <= budget_tokens:
                break
            content = contents[index]
            new_parts = []
            changed = False
            for part in content.parts or []:
                slim = _elide_part(part, kind)
                if slim is not None:
                    total -= _part_tokens(part) - _part_tokens(slim)
                    new_parts.append(slim)
                    changed = True
                    elided += 1
                else:
                    new_parts.append(part)
            if changed:
                contents[index] = types.Content(role=content.role, parts=new_parts)

    if total > budget_tokens:
        logger.warning(
            "Context harness: request still ~%d tokens after eliding %d part(s) (budget %d, fixed %d). "
            "Consider fewer enabled tools or a larger MODEL_CONTEXT_WINDOW.",
            total, elided, budget_tokens, fixed,
        )
    return elided


COMPACTED_USER_QUERY = (
    "[The earlier conversation, including my original request, was compacted "
    "into the summary that follows. Continue the task from it.]"
)


def ensure_user_query(llm_request) -> bool:
    """Guarantee the request carries a user text turn.

    ADK materializes a compaction summary as a *model* message, so once the
    user's request has been compacted a mid-task request can consist only of
    model turns and tool results. Many chat templates reject that (llama.cpp's
    Qwen template: "No user query found in messages"; Anthropic requires a
    leading user turn). Prepend a short user turn pointing at the summary.
    Returns True if a turn was inserted.
    """
    contents = llm_request.contents
    if contents is None:
        return False
    if any(c.role == "user" and any(p.text for p in c.parts or []) for c in contents):
        return False
    contents.insert(0, types.Content(role="user", parts=[types.Part(text=COMPACTED_USER_QUERY)]))
    return True


class ContextHarnessPlugin(BasePlugin):
    """App-wide plugin implementing the tool-output budget and the request guard."""

    def __init__(self, settings: HarnessSettings, name: str = "dak_context_harness"):
        super().__init__(name=name)
        self.settings = settings

    async def after_tool_callback(self, *, tool, tool_args, tool_context, result) -> Optional[dict]:
        tool_name = getattr(tool, "name", "tool")
        if tool_name == READ_TOOL_OUTPUT_NAME:
            return None  # already paged to the budget
        max_chars = self.settings.tool_output_chars
        text = _result_text(result)
        if text is None:
            return None
        if len(text) <= max_chars:
            return _drop_duplicate_structured_content(result, text)

        artifact = _artifact_name(tool_name, getattr(tool_context, "function_call_id", None))
        try:
            await tool_context.save_artifact(artifact, types.Part.from_text(text=text))
        except Exception as e:  # no artifact service configured
            logger.info("Context harness: could not offload %s output: %s", tool_name, e)
            artifact = None

        logger.info("Context harness: truncated %s output %d -> %d chars", tool_name, len(text), max_chars)
        replacement = {
            "result": _preview(text, max_chars),
            "truncated": True,
            "original_chars": len(text),
        }
        if isinstance(result, dict) and (result.get("isError") or result.get("is_error")):
            replacement["isError"] = True
        if artifact:
            replacement["full_output_artifact"] = artifact
            replacement["hint"] = (
                f"Output was too large for the context window. Use {READ_TOOL_OUTPUT_NAME}"
                f"(artifact_name='{artifact}', offset=..., pattern=...) to read the rest, "
                "or narrow the tool call."
            )
        else:
            replacement["hint"] = "Output was too large for the context window; narrow the tool call."
        return replacement

    async def before_model_callback(self, *, callback_context, llm_request) -> None:
        ensure_user_query(llm_request)
        fit_request_to_budget(llm_request, self.settings.request_token_budget)
        return None
