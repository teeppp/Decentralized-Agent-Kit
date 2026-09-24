import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dak_agent.adaptive_agent import AdaptiveAgent
from dak_agent.mode_manager import ModeManager, FIRST_TURN_DONE_KEY
from google.adk.tools import FunctionTool

class TestAdaptiveAgent(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tool1 = MagicMock()
        self.tool1.name = "tool1"
        self.tool2 = MagicMock()
        self.tool2.name = "tool2"
        self.mock_tools = [self.tool1, self.tool2]

    def test_initialization(self):
        """Test that the agent initializes with correct tools."""
        # Add switch_mode to mock tools to simulate real usage
        mock_switch = MagicMock(spec=FunctionTool)
        mock_switch.name = "switch_mode"
        tools = self.mock_tools + [mock_switch]

        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=tools
        )

        tool_names = [t.name for t in agent.tools if hasattr(t, 'name')]
        self.assertIn("switch_mode", tool_names)
        self.assertIn("list_skills", tool_names) # list_skills is added by AdaptiveAgent
        self.assertIn("enable_skill", tool_names) # enable_skill is added by AdaptiveAgent
        self.assertIn("tool1", tool_names)
        self.assertIn("tool2", tool_names)
        self.assertEqual(agent.model, "test-model")
        self.assertEqual(agent.name, "test_agent")
        self.assertIsInstance(agent._mode_manager, ModeManager)

    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_initial_turn_trigger(self, mock_generate_config):
        """Test that the first turn does NOT trigger a mode switch (starts with minimal tools)."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )

        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", ["tool1"], [])

        # Simulate callback (first turn)
        context = MagicMock()
        context.session.events = []
        context.state = {}
        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)

        # Verify Switch DID NOT happen (instruction remains same)
        self.assertEqual(agent.instruction, "Initial instruction")

        # Verify generate_mode_config NOT called
        mock_generate_config.assert_not_called()

        # Verify the first turn is recorded in this session's state (it happens
        # inside ModeManager.should_switch), not on the shared ModeManager instance.
        self.assertTrue(context.state.get(FIRST_TURN_DONE_KEY))

    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_large_context_does_not_trigger_switch(self, mock_generate_config):
        """Context pressure is the harness's job (ADK compaction), not a mode switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        event = MagicMock()
        event.content.parts = [MagicMock(text="a" * 1_000_000)]
        context = MagicMock()
        context.session.events = [event]
        context.state = {FIRST_TURN_DONE_KEY: True}

        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)

        self.assertEqual(agent.instruction, "Initial instruction")
        mock_generate_config.assert_not_called()
        self.assertEqual(len(context.session.events), 1)

    def test_history_summary_reads_session_events(self):
        """ADK sessions keep history in `events`; the summary must read them."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        event = MagicMock()
        event.content.parts = [MagicMock(text="please review the repo")]
        context = MagicMock()
        context.session.events = [event]

        self.assertIn("please review the repo", agent._extract_history_summary(context))

    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_switch_mode_tool_trigger(self, mock_generate_config):
        """Test that LLM calling switch_mode triggers a switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )

        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", ["tool1"], [])

        # Create LLM response with switch_mode tool call
        llm_response = MagicMock()
        mock_part = MagicMock()
        mock_part.function_call = MagicMock()
        mock_part.function_call.name = "switch_mode"
        mock_part.function_call.args = {"reason": "test", "new_focus": "debugging"}
        llm_response.content.parts = [mock_part]

        context = MagicMock()
        context.session.events = []
        # Bypass initial turn trigger for this session.
        context.state = {FIRST_TURN_DONE_KEY: True}
        # google-adk v2 runs the invocation on a copy of the agent; point the
        # mock's "live copy" back at `agent` itself so the assertions below
        # can observe the switch (see AdaptiveAgent._live_agent).
        context._invocation_context.agent = agent

        await agent._wrapped_callback(llm_response=llm_response, callback_context=context)

        # Verify Switch happened
        self.assertEqual(agent.instruction, "New Instruction")
        mock_generate_config.assert_called_once()

    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_first_turn_is_tracked_per_session(self, mock_generate_config):
        """Regression test: one AdaptiveAgent/ModeManager is shared by every
        session, so session A's first turn must not consume session B's."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        mock_generate_config.return_value = ("New Instruction", ["tool1"], [])

        session_a = MagicMock()
        session_a.session.events = []
        session_a.state = {}
        session_b = MagicMock()
        session_b.session.events = []
        session_b.state = {}

        # Session A's first turn.
        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=session_a)
        self.assertTrue(session_a.state.get(FIRST_TURN_DONE_KEY))

        # Session B's first turn must still be untouched by session A.
        self.assertFalse(session_b.state.get(FIRST_TURN_DONE_KEY, False))
        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=session_b)
        mock_generate_config.assert_not_called()
        self.assertTrue(session_b.state.get(FIRST_TURN_DONE_KEY))

    def test_call_instruction_overrides_mode_and_base_instruction(self):
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        state = {"dak_mode_instruction": "Mode instruction", "dak_active_skills": []}

        self.assertEqual(agent._resolve_session_instruction(state, {}), "Mode instruction")
        self.assertEqual(
            agent._resolve_session_instruction(state, {"dak:instruction": "Answer in one word."}),
            "Answer in one word.",
        )

    def _session_context(self, agent, state):
        context = MagicMock()
        context.state = state
        context._invocation_context.agent = MagicMock()
        return context

    def test_call_model_switches_live_model_when_allowed(self):
        agent = AdaptiveAgent(model="openai/default-model", name="test_agent",
                              instruction="Initial instruction", tools=self.mock_tools)
        context = self._session_context(agent, {"dak:model": "openai/allowed-model"})

        with patch.dict(os.environ, {"DAK_ALLOWED_MODELS": "openai/allowed-model"}):
            error = agent._apply_session_config(context)

        self.assertIsNone(error)
        live = context._invocation_context.agent
        self.assertEqual(live.model.model, "openai/allowed-model")
        # The LiteLlm is cached and shared across sessions, not rebuilt per call.
        other = self._session_context(agent, {"dak:model": "openai/allowed-model"})
        with patch.dict(os.environ, {"DAK_ALLOWED_MODELS": "openai/allowed-model"}):
            agent._apply_session_config(other)
        self.assertIs(other._invocation_context.agent.model, live.model)
        self.assertEqual(agent.model, "openai/default-model")  # the shared root is untouched

    async def test_call_model_rejected_returns_error_without_calling_llm(self):
        import json

        from google.adk.apps import App
        from google.adk.artifacts import InMemoryArtifactService
        from google.adk.models.base_llm import BaseLlm
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        calls = []

        class MustNotBeCalled(BaseLlm):
            async def generate_content_async(self, llm_request, stream=False):
                calls.append(llm_request)
                raise AssertionError("the LLM must not be called for a refused model")
                yield  # pragma: no cover

        agent = AdaptiveAgent(model=MustNotBeCalled(model="default-model"), name="dak_agent",
                              instruction="Initial instruction", tools=[])
        sessions = InMemorySessionService()
        session = await sessions.create_session(app_name="dak_agent", user_id="u")
        runner = Runner(app=App(name="dak_agent", root_agent=agent), session_service=sessions,
                        artifact_service=InMemoryArtifactService())

        texts = []
        with patch.dict(os.environ, {"DAK_ALLOWED_MODELS": "openai/allowed-model"}), \
                patch("dak_agent.remote_tools.discover_remote_tools", return_value={}):
            async for event in runner.run_async(
                user_id="u", session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
                state_delta={"dak:model": "openai/not-allowed"},
            ):
                texts += [p.text for p in (event.content.parts if event.content else []) if p.text]

        self.assertEqual(calls, [])
        error = json.loads(texts[-1])
        self.assertEqual(error["error"], "model_not_allowed")
        self.assertEqual(error["requested_model"], "openai/not-allowed")
        self.assertEqual(error["allowed_models"], ["openai/allowed-model"])

    async def test_call_model_rejected_even_when_session_config_fails(self):
        """A broken piece of session state must not turn the refusal into a
        silent fall-through to the default model (fail closed)."""
        import json

        agent = AdaptiveAgent(model="openai/default-model", name="test_agent",
                              instruction="Initial instruction", tools=self.mock_tools)
        context = self._session_context(agent, {"dak:model": "openai/not-allowed", "dak_active_skills": None})

        with patch.dict(os.environ, {"DAK_ALLOWED_MODELS": "openai/allowed-model"}):
            content = await agent._restore_session_config(context)

        self.assertIsNotNone(content)
        self.assertEqual(json.loads(content.parts[0].text)["error"], "model_not_allowed")

if __name__ == '__main__':
    unittest.main()
