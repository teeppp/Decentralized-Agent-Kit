import unittest
from unittest.mock import MagicMock
from dak_agent.mode_manager import ModeManager

class TestModeManager(unittest.TestCase):
    def setUp(self):
        self.mode_manager = ModeManager()
        self.mock_client = MagicMock()
        
        # Create mock tools
        self.tool_switch = MagicMock()
        self.tool_switch.name = "switch_mode"
        self.tool_planner = MagicMock()
        self.tool_planner.name = "planner"
        self.tool_read = MagicMock()
        self.tool_read.name = "read_file"
        
        self.available_tools = [self.tool_switch, self.tool_planner, self.tool_read]

    def test_returns_selected_tool_names(self):
        """Test that generate_mode_config returns tool names as strings."""
        mock_response = MagicMock()
        mock_response.text = '{"instruction": "Read file", "selected_tools": ["read_file", "deep_think"]}'
        self.mock_client.models.generate_content.return_value = mock_response
        
        instruction, selected_tool_names = self.mode_manager.generate_mode_config(
            history_summary="test",
            available_tools=self.available_tools,
            model_client=self.mock_client
        )
        
        # Verify returns list of strings (tool names)
        self.assertIn("read_file", selected_tool_names)
        self.assertIn("deep_think", selected_tool_names)
        self.assertEqual(instruction, "Read file")
        
    def test_returns_empty_list_on_error(self):
        """Test that generate_mode_config returns empty list on LLM error."""
        self.mock_client.models.generate_content.side_effect = Exception("API Error")
        
        instruction, selected_tool_names = self.mode_manager.generate_mode_config(
            history_summary="test",
            available_tools=self.available_tools,
            model_client=self.mock_client
        )
        
        # Should return empty list and default instruction
        self.assertEqual(selected_tool_names, [])
        self.assertEqual(instruction, "Continue with current task.")

if __name__ == '__main__':
    unittest.main()
