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

    def test_litellm_prefix_stripped_for_token_lookup(self):
        """A LiteLLM-prefixed model name still resolves its context window size."""
        manager = ModeManager(model_name="gemini/gemini-2.5-flash")
        self.assertEqual(manager.max_context_tokens, ModeManager.MODEL_MAX_TOKENS["gemini-2.5-flash"])

if __name__ == '__main__':
    unittest.main()
