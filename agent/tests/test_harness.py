"""Tests for the context-engineering harness (dak_agent/harness.py)."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from dak_agent import harness
from dak_agent.harness import (
    BudgetedEventSummarizer,
    ContextHarnessPlugin,
    HarnessSettings,
    estimate_tokens,
    fit_request_to_budget,
    is_context_overflow_error,
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
        assert isinstance(config.summarizer, BudgetedEventSummarizer)
        assert "User request" in config.summarizer._prompt_template

    def test_compaction_budgets_derive_from_window(self):
        s = HarnessSettings(context_window=32768)
        assert s.compaction_input_tokens == 16384  # half the window; the rest is for the summary
        assert s.compaction_entry_chars == 1638
        assert HarnessSettings(context_window=8192).compaction_entry_chars == 409
        assert HarnessSettings(context_window=4096).compaction_entry_chars == 400  # floor
        assert HarnessSettings(context_window=1_000_000).compaction_entry_chars == 2000  # cap


# --- Budgeted compaction summarizer -----------------------------------------


def _event(author, *, text=None, thought=None, call=None, response=None, ts=1.0):
    from google.adk.events.event import Event

    parts = []
    if thought:
        parts.append(types.Part(text=thought, thought=True))
    if text:
        parts.append(types.Part(text=text))
    if call:
        parts.append(types.Part(function_call=types.FunctionCall(id="fc", name=call[0], args=call[1])))
    if response:
        parts.append(types.Part(function_response=types.FunctionResponse(
            id="fc", name=response[0], response=response[1])))
    return Event(author=author, content=types.Content(role="model" if author != "user" else "user", parts=parts),
                 timestamp=ts, invocation_id="inv")


def _summarizer_llm(responses):
    """LLM whose `generate_content_async` yields/raises per `responses` (in order); records prompts."""
    from google.adk.models.llm_response import LlmResponse

    llm = MagicMock()
    llm.model = "scripted"
    llm.prompts = []
    queue = list(responses)

    async def generate_content_async(llm_request, stream=False):
        llm.prompts.append(llm_request.contents[0].parts[0].text)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        # A reasoning model returns its thoughts alongside the summary.
        parts = [types.Part(text="Let me compact this...", thought=True), types.Part(text=item)]
        yield LlmResponse(content=types.Content(role="model", parts=parts),
                          usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=1))

    llm.generate_content_async = generate_content_async
    return llm


def _context_error():
    import litellm

    return litellm.ContextWindowExceededError(
        message="request (50848 tokens) exceeds the available context size (32768 tokens)",
        model="scripted", llm_provider="openai")


class TestContextOverflowClassification:
    def test_litellm_class(self):
        assert is_context_overflow_error(_context_error())

    def test_llamacpp_message(self):
        assert is_context_overflow_error(ValueError("request (50848 tokens) exceeds the available context size"))

    def test_other_errors(self):
        assert not is_context_overflow_error(ConnectionError("connection refused"))
        assert not is_context_overflow_error(ValueError("No user query found in messages"))
        assert not is_context_overflow_error(ValueError("Model does not support context window caching"))


class TestBudgetedEventSummarizer:
    settings = HarnessSettings(context_window=8192)  # entry cap 409 chars, input budget 4096 tokens

    def _events(self, thought_chars=6000, n=6):
        # Mirrors the wedged session: a rolling summary seed, then thought-heavy tool turns.
        events = [_event("model", text="User request: 調査して。Progress: docs を読んだ。" * 10, ts=0.5)]
        for i in range(n):
            events.append(_event("dak_agent", thought="考察" * (thought_chars // 2), call=("read_file", {"path": f"f{i}"}),
                                 ts=float(i + 1)))
            events.append(_event("dak_agent", response=("read_file", {"result": "x" * 3000}), ts=float(i + 1) + 0.5))
        return events

    @pytest.mark.asyncio
    async def test_thought_heavy_history_is_fitted_to_the_input_budget(self):
        summarizer = BudgetedEventSummarizer(_summarizer_llm(["summary"]), self.settings)
        events = self._events()
        # ADK's summarizer would send every thought verbatim: ~30K tokens on an 8K window.
        assert sum(estimate_tokens(p.text) for e in events for p in e.content.parts if p.thought) > 30_000

        event = await summarizer.maybe_summarize_events(events=events)

        prompt = summarizer._llm.prompts[0]
        assert estimate_tokens(prompt) <= self.settings.compaction_input_tokens
        assert "called tool: read_file" in prompt and "truncated" in prompt
        assert "User request: 調査して" in prompt  # the dense seed survives
        assert [p.text for p in event.actions.compaction.compacted_content.parts] == ["summary"]  # no thoughts
        assert event.actions.compaction.start_timestamp == 0.5
        assert event.actions.compaction.end_timestamp == 6.5

    def test_streamed_thought_fragments_become_one_entry(self):
        # Streaming stored one turn of reasoning as ~150 thought parts of a few chars each.
        from google.adk.events.event import Event

        parts = [types.Part(text=f"断片{i}", thought=True) for i in range(150)]
        parts.append(types.Part(function_call=types.FunctionCall(id="fc", name="list_skills", args={})))
        event = Event(author="dak_agent", content=types.Content(role="model", parts=parts), timestamp=1.0,
                      invocation_id="inv")
        summarizer = BudgetedEventSummarizer(_summarizer_llm([]), self.settings)

        entries = summarizer._history_entries([event])

        assert [e.kind for e in entries] == ["thought", "call"]
        assert entries[0].text.startswith("dak_agent (thought): 断片0断片1")

    def test_separate_events_are_not_merged(self):
        summarizer = BudgetedEventSummarizer(_summarizer_llm([]), self.settings)
        entries = summarizer._history_entries([
            _event("dak_agent", text="First answer.", ts=1.0), _event("dak_agent", text="Second answer.", ts=2.0)])
        assert [e.text for e in entries] == ["dak_agent: First answer.", "dak_agent: Second answer."]

    def test_fit_never_drops_the_last_entry(self):
        summarizer = BudgetedEventSummarizer(_summarizer_llm([]), self.settings)
        entries = summarizer._history_entries(
            [_event("user", response=("planner", {"result": "x" * 3000}), ts=float(i)) for i in range(5)])
        rendered = summarizer._fit_history(entries, budget_tokens=5)
        assert len(rendered) == 1

    @pytest.mark.asyncio
    async def test_retry_stops_early_when_nothing_is_left_to_shrink(self):
        llm = _summarizer_llm([_context_error()] * 3)
        summarizer = BudgetedEventSummarizer(llm, HarnessSettings(context_window=512))  # budget already tiny

        event = await summarizer.maybe_summarize_events(events=self._events(n=1))

        assert len(llm.prompts) < 3  # identical prompts are not re-sent
        assert event.actions.compaction.compacted_content.parts[0].text.startswith("[Automatic excerpt")

    @pytest.mark.asyncio
    async def test_thought_only_summary_falls_back_to_the_excerpt(self):
        """A reasoning model that ran out of output tokens returns thoughts only."""
        from google.adk.models.llm_response import LlmResponse

        llm = _summarizer_llm([])

        async def thoughts_only(llm_request, stream=False):
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="hmm", thought=True)]))

        llm.generate_content_async = thoughts_only
        summarizer = BudgetedEventSummarizer(llm, self.settings)

        event = await summarizer.maybe_summarize_events(events=self._events())

        parts = event.actions.compaction.compacted_content.parts
        assert len(parts) == 1 and not parts[0].thought
        assert parts[0].text.startswith("[Automatic excerpt")

    def test_fit_loses_bulk_before_facts(self):
        summarizer = BudgetedEventSummarizer(_summarizer_llm([]), self.settings)
        entries = summarizer._history_entries(self._events(n=40))
        rendered = summarizer._fit_history(entries, budget_tokens=600)
        # Oldest bulky entries were dropped; the first dense entry never is.
        assert rendered[0].startswith("model: User request: 調査して")
        assert sum(estimate_tokens(r) for r in rendered) <= 600
        assert len(rendered) < len(entries)
        assert rendered[-1].startswith("Tool response from read_file")  # newest kept

    @pytest.mark.asyncio
    async def test_context_error_halves_the_budget_and_retries(self):
        llm = _summarizer_llm([_context_error(), "summary"])
        summarizer = BudgetedEventSummarizer(llm, self.settings)

        event = await summarizer.maybe_summarize_events(events=self._events())

        assert event is not None
        assert len(llm.prompts) == 2
        assert estimate_tokens(llm.prompts[1]) < estimate_tokens(llm.prompts[0])

    @pytest.mark.asyncio
    async def test_persistent_context_error_falls_back_to_an_excerpt(self):
        """The wedged-session case: instead of raising on every turn, compact anyway."""
        llm = _summarizer_llm([_context_error()] * 3)
        summarizer = BudgetedEventSummarizer(llm, self.settings)

        event = await summarizer.maybe_summarize_events(events=self._events())

        assert len(llm.prompts) == 3
        text = event.actions.compaction.compacted_content.parts[0].text
        assert text.startswith("[Automatic excerpt")
        assert "User request: 調査して" in text
        assert event.actions.compaction.compacted_content.role == "model"

    @pytest.mark.asyncio
    async def test_other_model_errors_skip_compaction_instead_of_raising(self):
        llm = _summarizer_llm([ConnectionError("llama-server is down")])
        summarizer = BudgetedEventSummarizer(llm, self.settings)

        assert await summarizer.maybe_summarize_events(events=self._events()) is None

    @pytest.mark.asyncio
    async def test_empty(self):
        summarizer = BudgetedEventSummarizer(_summarizer_llm([]), self.settings)
        assert await summarizer.maybe_summarize_events(events=[]) is None


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
    def test_thoughts_count_and_old_unsigned_ones_are_dropped_first(self):
        # LiteLLM sends stored reasoning back (`reasoning_content`) and the Qwen3
        # template renders it, so thoughts must be budgeted and are the first to go.
        assert harness._part_tokens(types.Part(text="a" * 400, thought=True)) == 100
        request = LlmRequest(contents=[
            types.Content(role="user", parts=[types.Part(text="q")]),
            types.Content(role="model", parts=[
                types.Part(text="x" * 4000, thought=True),
                types.Part(text="y" * 4000, thought=True, thought_signature=b"sig"),
                types.Part(function_call=types.FunctionCall(id="1", name="t", args={}))]),
            types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
                id="1", name="t", response={"result": "z" * 2000}))]),
            types.Content(role="user", parts=[types.Part(text="next")]),
        ])
        elided = fit_request_to_budget(request, budget_tokens=2000, keep_last=1)
        parts = request.contents[1].parts
        assert elided == 1
        assert [bool(p.thought_signature) for p in parts if p.thought] == [True]  # unsigned gone, signed kept
        assert parts[-1].function_call is not None
        assert request.contents[2].parts[0].function_response.response == {"result": "z" * 2000}  # untouched

    def test_thought_only_turn_is_not_left_empty(self):
        request = LlmRequest(contents=[
            types.Content(role="model", parts=[types.Part(text="x" * 4000, thought=True)]),
            types.Content(role="user", parts=[types.Part(text="next")]),
        ])
        fit_request_to_budget(request, budget_tokens=100, keep_last=1)
        assert request.contents[0].parts == [types.Part(text="[thoughts elided]")]

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


    def test_never_guts_the_compaction_summary(self):
        """The summary is a model-role text part; eliding it would drop the task
        the request has just been told to continue."""
        summary = types.Content(role="model", parts=[types.Part(text="User request: " + "s" * 3000)])
        request = LlmRequest(contents=[summary, _fr("a", 4000), _fr("b", 4000),
                                       types.Content(role="user", parts=[types.Part(text="hi")])])

        fit_request_to_budget(request, budget_tokens=10, keep_last=1)

        assert request.contents[0] is summary
        assert len(summary.parts[0].text) == len("User request: ") + 3000


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


# ~3.4K CJK chars of reasoning per step, stored the way streaming stores it:
# one thought part of a few chars per chunk (the wedged session had ~5,600 of
# them for 23K chars). ADK's summarizer renders each on its own prefixed line.
THOUGHT_FRAGMENTS = ["考える。"] * 850


def _make_fake_llm(tool_calls: int, thoughts: bool = False):
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse

    class ScriptedLlm(BaseLlm):
        """Calls big_tool `tool_calls` times, then answers. Records request sizes."""
        steps: int = 0
        request_tokens: list = []
        summary_tokens: list = []
        summaries: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            tokens = _request_tokens(llm_request)
            usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=tokens)
            text = "".join(p.text or "" for c in llm_request.contents for p in c.parts or [])
            if "compacting the working memory" in text or "conversation history between a user" in text:
                self.summary_tokens.append(tokens)
                if tokens > WINDOW:
                    raise ValueError(f"the request exceeds the available context size ({tokens} > {WINDOW})")
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
            parts = [types.Part(text=f, thought=True) for f in THOUGHT_FRAGMENTS] + [part] if thoughts else [part]
            yield LlmResponse(content=types.Content(role="model", parts=parts), usage_metadata=usage)

    return ScriptedLlm(model="scripted")


async def _run(use_harness: bool, tool_calls: int = 6, thoughts: bool = False, adk_summarizer: bool = False):
    from google.adk.agents import LlmAgent
    from google.adk.apps import App
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.tools import FunctionTool

    llm = _make_fake_llm(tool_calls, thoughts=thoughts)
    settings = HarnessSettings(context_window=WINDOW)
    tools = [FunctionTool(big_tool)]
    if use_harness:
        tools.append(make_read_tool_output_tool(settings.tool_output_chars))
    agent = LlmAgent(name="dak_agent", model=llm, instruction="Inspect the logs.", tools=tools)
    compaction = make_compaction_config(settings, llm=llm) if use_harness else None
    if compaction is not None and adk_summarizer:
        from google.adk.apps.llm_event_summarizer import LlmEventSummarizer

        compaction.summarizer = LlmEventSummarizer(llm=llm)  # what shipped before this fix
    app = App(
        name="dak_agent",
        root_agent=agent,
        plugins=[ContextHarnessPlugin(settings)] if use_harness else [],
        events_compaction_config=compaction,
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


@pytest.mark.asyncio
async def test_adk_summarizer_overflows_on_a_reasoning_model():
    """Reproduces the 2026-09-14 wedge: thoughts are not in the model prompt, but
    ADK's summarizer renders them verbatim, so the *compaction* request overflows."""
    llm, _, final_text, error, _ = await _run(use_harness=True, thoughts=True, adk_summarizer=True)
    assert error is not None and "context size" in str(error)
    assert final_text is None
    assert max(llm.summary_tokens) > WINDOW
    assert max(llm.request_tokens) <= WINDOW  # the request guard did its job; compaction killed the run


@pytest.mark.asyncio
async def test_budgeted_summarizer_keeps_compaction_inside_the_window():
    llm, session, final_text, error, _ = await _run(use_harness=True, thoughts=True)

    assert error is None
    assert final_text == "done"
    assert llm.summaries >= 1
    assert max(llm.summary_tokens) <= WINDOW
    assert max(llm.request_tokens) <= WINDOW
