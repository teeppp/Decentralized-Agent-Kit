"""Tests for the context-engineering harness (dak_agent/harness.py)."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from dak_agent import harness
from dak_agent.harness import (
    ContextHarnessPlugin,
    HarnessSettings,
    estimate_tokens,
    fit_request_to_budget,
    make_compaction_config,
    make_read_tool_output_tool,
)


def _tool(name="read_file"):
    tool = MagicMock()
    tool.name = name
    return tool


def _tool_context(save_side_effect=None):
    ctx = MagicMock()
    ctx.function_call_id = "call-1"
    ctx.save_artifact = AsyncMock(side_effect=save_side_effect)
    return ctx


class TestEstimateTokens:
    def test_ascii_is_about_four_chars_per_token(self):
        assert estimate_tokens("a" * 400) == 100

    def test_cjk_counts_one_token_per_char(self):
        # len // 4 would say 25 and let a Japanese prompt overflow an 8K model.
        assert estimate_tokens("日本語" * 33 + "a") == 99

    def test_empty(self):
        assert estimate_tokens("") == 0


class TestHarnessSettings:
    def test_small_local_window_gets_tight_budgets(self):
        s = HarnessSettings(context_window=8192)
        assert s.compaction_token_threshold == 4915
        assert s.request_token_budget == 6963
        assert s.tool_output_chars == 2000  # floor

    def test_large_window_tool_output_is_capped(self):
        assert HarnessSettings(context_window=1_000_000).tool_output_chars == 40_000

    @patch.dict(os.environ, {"MODEL_CONTEXT_WINDOW": "8192", "DAK_TOOL_OUTPUT_MAX_CHARS": "1234",
                             "DAK_COMPACTION_THRESHOLD_RATIO": "0.5", "DAK_COMPACTION_RETAIN_EVENTS": "2"})
    def test_from_env(self):
        s = HarnessSettings.from_env("openai/llamacpp")
        assert s.context_window == 8192
        assert s.tool_output_chars == 1234
        assert s.compaction_token_threshold == 4096
        assert s.compaction_retain_events == 2

    @patch.dict(os.environ, {"MODEL_CONTEXT_WINDOW": "8192", "DAK_COMPACTION_THRESHOLD_RATIO": "7",
                             "DAK_COMPACTION_RETAIN_EVENTS": "-1"})
    def test_invalid_env_falls_back_to_defaults(self):
        s = HarnessSettings.from_env("openai/llamacpp")
        assert s.compaction_threshold_ratio == 0.6
        assert s.compaction_retain_events == 4

    def test_compaction_config_uses_token_threshold(self):
        config = make_compaction_config(HarnessSettings(context_window=8192), llm=MagicMock())
        assert config.token_threshold == 4915
        assert config.event_retention_size == 4
        assert "User request" in config.summarizer._prompt_template


class TestToolOutputBudget:
    plugin = ContextHarnessPlugin(HarnessSettings(context_window=8192))  # 2000 chars

    @pytest.mark.asyncio
    async def test_small_result_untouched(self):
        result = await self.plugin.after_tool_callback(
            tool=_tool(), tool_args={}, tool_context=_tool_context(), result="short")
        assert result is None

    @pytest.mark.asyncio
    async def test_mcp_structured_duplicate_dropped(self):
        mcp_result = {"content": [{"type": "text", "text": "hello"}],
                      "structuredContent": {"result": "hello"}, "isError": False}
        result = await self.plugin.after_tool_callback(
            tool=_tool(), tool_args={}, tool_context=_tool_context(), result=mcp_result)
        assert result == {"content": [{"type": "text", "text": "hello"}], "isError": False}

    @pytest.mark.asyncio
    async def test_large_result_truncated_and_offloaded(self):
        text = "".join(f"line {i}\n" for i in range(2000))
        ctx = _tool_context()
        mcp_result = {"content": [{"type": "text", "text": text}], "structuredContent": {"result": text}}
        result = await self.plugin.after_tool_callback(
            tool=_tool(), tool_args={}, tool_context=ctx, result=mcp_result)

        assert result["truncated"] is True
        assert result["original_chars"] == len(text)
        assert len(result["result"]) < 2100
        assert result["result"].startswith("line 0\n")
        assert result["result"].rstrip().endswith("line 1999")
        assert result["full_output_artifact"] == "tool_output_read_file_call-1.txt"
        saved_name, saved_part = ctx.save_artifact.call_args.args
        assert saved_name == result["full_output_artifact"]
        assert saved_part.text == text

    @pytest.mark.asyncio
    async def test_without_artifact_service_still_truncates(self):
        ctx = _tool_context(save_side_effect=ValueError("Artifact service is not initialized."))
        result = await self.plugin.after_tool_callback(
            tool=_tool(), tool_args={}, tool_context=ctx, result="x" * 10_000)
        assert result["truncated"] is True
        assert "full_output_artifact" not in result
        assert "narrow the tool call" in result["hint"]

    @pytest.mark.asyncio
    async def test_media_results_untouched(self):
        mcp_result = {"content": [{"type": "image", "data": "x" * 10_000, "mimeType": "image/png"}]}
        result = await self.plugin.after_tool_callback(
            tool=_tool(), tool_args={}, tool_context=_tool_context(), result=mcp_result)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_tool_output_is_exempt(self):
        result = await self.plugin.after_tool_callback(
            tool=_tool(harness.READ_TOOL_OUTPUT_NAME), tool_args={}, tool_context=_tool_context(),
            result={"content": "x" * 10_000})
        assert result is None


class TestReadToolOutput:
    def _ctx(self, text):
        ctx = MagicMock()
        ctx.load_artifact = AsyncMock(return_value=types.Part.from_text(text=text))
        return ctx

    @pytest.mark.asyncio
    async def test_pages_through_output(self):
        tool = make_read_tool_output_tool(max_chars=100)
        ctx = self._ctx("abcdefghij" * 25)
        first = await tool.func(artifact_name="a.txt", tool_context=ctx)
        assert len(first["content"]) == 100 and first["next_offset"] == 100 and not first["done"]
        last = await tool.func(artifact_name="a.txt", offset=200, limit=500, tool_context=ctx)
        assert len(last["content"]) == 50 and last["done"]

    @pytest.mark.asyncio
    async def test_pattern_returns_matching_lines(self):
        tool = make_read_tool_output_tool(max_chars=1000)
        ctx = self._ctx("alpha\nbeta\nalphabet\n")
        result = await tool.func(artifact_name="a.txt", pattern="^alpha", tool_context=ctx)
        assert result["matches"] == "1: alpha\n3: alphabet"
        assert result["match_count"] == 2

    @pytest.mark.asyncio
    async def test_missing_artifact(self):
        ctx = MagicMock()
        ctx.load_artifact = AsyncMock(return_value=None)
        tool = make_read_tool_output_tool(max_chars=100)
        assert "error" in await tool.func(artifact_name="nope", tool_context=ctx)


def _fr(name, size):
    return types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
        id=f"id-{name}", name=name, response={"result": "z" * size}))])


class TestRequestBudgetGuard:
    def test_under_budget_is_noop(self):
        request = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="hi")])])
        assert fit_request_to_budget(request, budget_tokens=100) == 0

    def test_elides_oldest_tool_payloads_first(self):
        old, mid = _fr("old", 4000), _fr("mid", 4000)
        recent = [types.Content(role="model", parts=[types.Part(text="thinking")]), _fr("new", 4000)]
        request = LlmRequest(contents=[old, mid, *recent])

        elided = fit_request_to_budget(request, budget_tokens=2200, keep_last=2)

        assert elided == 1  # dropping "old" alone gets under budget
        assert "elided" in request.contents[0].parts[0].function_response.response["result"]
        assert request.contents[0].parts[0].function_response.id == "id-old"
        assert request.contents[1] is mid
        assert request.contents[2:] == recent
        # The session's own Content object must not be mutated.
        assert old.parts[0].function_response.response["result"] == "z" * 4000


class TestEnsureUserQuery:
    def test_inserts_user_turn_when_only_model_and_tool_turns_remain(self):
        summary = types.Content(role="model", parts=[types.Part(text="User request: ...")])
        request = LlmRequest(contents=[summary, _fr("read_file", 10)])
        assert harness.ensure_user_query(request) is True
        assert request.contents[0].role == "user"
        assert request.contents[1] is summary

    def test_noop_when_user_text_present(self):
        request = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="hi")]),
                                       _fr("read_file", 10)])
        assert harness.ensure_user_query(request) is False
        assert len(request.contents) == 2


# --- End-to-end: a real ADK Runner with a scripted model --------------------

WINDOW = 8192
BIG_OUTPUT = "日本語のログ行です\n" * 4000  # ~40K chars, CJK-heavy like a real Japanese session


def big_tool() -> str:
    """Return a huge log."""
    return BIG_OUTPUT


def _request_tokens(llm_request) -> int:
    return harness._fixed_request_tokens(llm_request) + sum(
        harness._content_tokens(c) for c in llm_request.contents or [])


def _make_fake_llm(tool_calls: int):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse

    class ScriptedLlm(BaseLlm):
        """Calls big_tool `tool_calls` times, then answers. Records request sizes."""
        steps: int = 0
        request_tokens: list = []
        summaries: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            tokens = _request_tokens(llm_request)
            usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=tokens)
            text = "".join(p.text or "" for c in llm_request.contents for p in c.parts or [])
            if "compacting the working memory" in text:
                self.summaries += 1
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
                    text="User request: inspect logs. Progress: read logs.")]), usage_metadata=usage)
                return
            self.request_tokens.append(tokens)
            if not any(c.role == "user" and any(p.text for p in c.parts or []) for c in llm_request.contents):
                # Mirrors llama.cpp's Qwen chat template (--jinja).
                raise ValueError("Jinja Exception: No user query found in messages.")
            if tokens > WINDOW:
                raise ValueError(f"the request exceeds the available context size ({tokens} > {WINDOW})")
            self.steps += 1
            if self.steps <= tool_calls:
                part = types.Part(function_call=types.FunctionCall(
                    id=f"fc-{self.steps}", name="big_tool", args={}))
            else:
                part = types.Part(text="done")
            yield LlmResponse(content=types.Content(role="model", parts=[part]), usage_metadata=usage)

    return ScriptedLlm(model="scripted")


async def _run(use_harness: bool, tool_calls: int = 6):
    from google.adk.agents import LlmAgent
    from google.adk.apps import App
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import FunctionTool

    llm = _make_fake_llm(tool_calls)
    settings = HarnessSettings(context_window=WINDOW)
    tools = [FunctionTool(big_tool)]
    if use_harness:
        tools.append(make_read_tool_output_tool(settings.tool_output_chars))
    agent = LlmAgent(name="dak_agent", model=llm, instruction="Inspect the logs.", tools=tools)
    app = App(
        name="dak_agent",
        root_agent=agent,
        plugins=[ContextHarnessPlugin(settings)] if use_harness else [],
        events_compaction_config=make_compaction_config(settings, llm=llm) if use_harness else None,
    )
    sessions = InMemorySessionService()
    artifacts = InMemoryArtifactService()
    runner = Runner(app=app, session_service=sessions, artifact_service=artifacts)
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    final_text = None
    error = None
    try:
        async for event in runner.run_async(
            user_id="u", session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text="ログを全部読んで要約して")]),
        ):
            for part in (event.content.parts if event.content else None) or []:
                if part.text and not part.thought:
                    final_text = part.text
    except ValueError as e:
        error = e
    session = await sessions.get_session(app_name="dak_agent", user_id="u", session_id=session.id)
    return llm, session, final_text, error, artifacts


@pytest.mark.asyncio
async def test_without_harness_a_long_tool_loop_overflows_the_window():
    """Reproduces the reported failure: one request, several big tool results."""
    llm, _, final_text, error, _ = await _run(use_harness=False)
    assert error is not None and "context size" in str(error)
    assert final_text is None


@pytest.mark.asyncio
async def test_harness_keeps_every_request_inside_the_window():
    llm, session, final_text, error, artifacts = await _run(use_harness=True)

    assert error is None
    assert final_text == "done"
    assert llm.steps == 7
    assert max(llm.request_tokens) <= WINDOW
    # Compaction ran inside the single invocation and left a summary event.
    assert llm.summaries >= 1
    assert any(e.actions.compaction for e in session.events)
    # Full outputs were offloaded for read_tool_output.
    keys = await artifacts.list_artifact_keys(app_name="dak_agent", user_id="u", session_id=session.id)
    assert any(k.startswith("tool_output_big_tool") for k in keys)
