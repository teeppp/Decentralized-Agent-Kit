import unittest
from unittest.mock import MagicMock, patch
from dak_agent.mode_manager import ModeManager

class TestModeManager(unittest.TestCase):
    def setUp(self):
        self.mode_manager = ModeManager()

        # Create mock tools
        self.tool_switch = MagicMock()
        self.tool_switch.name = "switch_mode"
        self.tool_planner = MagicMock()
        self.tool_planner.name = "planner"
        self.tool_read = MagicMock()
        self.tool_read.name = "read_file"

        self.available_tools = [self.tool_switch, self.tool_planner, self.tool_read]

    @patch("dak_agent.mode_manager.meta_llm.complete_json")
    def test_returns_selected_tool_names(self, mock_complete_json):
        """Test that generate_mode_config returns tool names as strings."""
        mock_complete_json.return_value = {
            "instruction": "Read file",
            "selected_tools": ["read_file", "deep_think"],
        }

        instruction, selected_tool_names, selected_skills = self.mode_manager.generate_mode_config(
            history_summary="test",
            available_tools=self.available_tools,
            available_skills=[],
        )

        # Verify returns list of strings (tool names)
        self.assertIn("read_file", selected_tool_names)
        self.assertIn("deep_think", selected_tool_names)
        self.assertEqual(instruction, "Read file")

    @patch("dak_agent.mode_manager.meta_llm.complete_json")
    def test_returns_empty_list_on_error(self, mock_complete_json):
        """Test that generate_mode_config returns empty list on LLM error."""
        mock_complete_json.side_effect = Exception("API Error")

        instruction, selected_tool_names, selected_skills = self.mode_manager.generate_mode_config(
            history_summary="test",
            available_tools=self.available_tools,
            available_skills=[],
        )

        # Should return empty list and default instruction
        self.assertEqual(selected_tool_names, [])
        self.assertEqual(instruction, "Continue with current task.")

    def test_litellm_prefix_resolves_context_window(self):
        """A LiteLLM-prefixed model name still resolves its context window size."""
        manager = ModeManager(model_name="gemini/gemini-2.5-flash")
        self.assertGreater(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["default"])

    def test_bedrock_claude_resolves_context_window(self):
        """Bedrock inference-profile IDs resolve via litellm's model map."""
        manager = ModeManager(model_name="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0")
        self.assertEqual(manager.max_context_tokens, 200000)

    def test_bedrock_claude_large_window_not_underestimated(self):
        """1M-window Bedrock Claude must not be clamped to the 200K family guess."""
        manager = ModeManager(model_name="bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.assertEqual(manager.max_context_tokens, 1000000)

    def test_bedrock_gpt56_resolves_context_window(self):
        manager = ModeManager(model_name="bedrock/us.openai.gpt-5.6-luna")
        self.assertEqual(manager.max_context_tokens, 1000000)

    def test_unknown_model_uses_default_context_window(self):
        """IDs litellm can't map (e.g. a llama-server alias) get the conservative default."""
        manager = ModeManager(model_name="openai/llamacpp")
        self.assertEqual(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["default"])

    def test_model_without_map_entry_tokens_uses_default(self):
        """litellm entries with max_input_tokens=None fall back to the default."""
        manager = ModeManager(model_name="ollama_chat/llama3.1:8b")
        self.assertEqual(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["default"])

    def test_default_model_resolves_full_context_window(self):
        """The default model (newer than litellm's map) resolves via the override table."""
        manager = ModeManager()
        self.assertEqual(
            manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["gemini-3.7-flash"]
        )
        self.assertNotEqual(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["default"])

    def test_gemini_3x_resolves_context_window_via_litellm(self):
        """Gemini 3.x IDs that litellm already maps resolve without an override entry."""
        manager = ModeManager(model_name="gemini/gemini-3.5-flash-lite")
        self.assertGreater(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["default"])

    def test_requested_focus_is_consumed_once(self):
        """A stale LLM-requested focus must not leak into later automatic switches."""
        self.mode_manager.request_switch(reason="need tools", new_focus="deploy the app")
        self.assertEqual(self.mode_manager.consume_requested_focus(), "deploy the app")
        self.assertIsNone(self.mode_manager.consume_requested_focus())

    def test_reset_session_clears_requested_focus(self):
        self.mode_manager.request_switch(reason="need tools", new_focus="deploy the app")
        self.mode_manager.reset_session()
        self.assertIsNone(self.mode_manager.consume_requested_focus())

if __name__ == '__main__':
    unittest.main()
