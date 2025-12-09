import unittest
from unittest.mock import MagicMock, patch
from dak_agent.mode_manager import ModeManager
from google.adk.tools import FunctionTool

class TestGenericEscapeHatch(unittest.TestCase):
    
    def setUp(self):
        self.mode_manager = ModeManager(model_name="test-model")
        
    def test_generic_instruction_injection(self):
        # Create mock tools
        tools = []
        
        t1 = MagicMock()
        t1.name = "read_file"
        t1.description = "Read a file"
        tools.append(t1)
        
        # Mock LLM client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"instruction": "New instruction", "selected_tools": ["read_file"]}'
        mock_client.models.generate_content.return_value = mock_response
        
        # Call generate_mode_config
        self.mode_manager.generate_mode_config(
            history_summary="Test summary",
            available_tools=tools,
            model_client=mock_client
        )
        
        # Verify that the prompt sent to the LLM contains the generic instruction
        call_args = mock_client.models.generate_content.call_args
        prompt_sent = call_args.kwargs['contents']
        
        # Check for key phrases in the prompt
        self.assertIn("If the user requests an action that requires tools you do not currently have", prompt_sent)
        self.assertIn("MUST follow this 2-step process", prompt_sent)
        self.assertIn("Call `switch_mode(request_tool_list=True)`", prompt_sent)
        
        # Verify NO specific categories are mentioned (unless they are in tool descriptions)
        self.assertNotIn("Capability Summary", prompt_sent)
        self.assertNotIn("File System", prompt_sent) # Should not be in the INSTRUCTION part (it is in tool desc, but we check prompt text)
        # Note: "File System" might appear if we categorized, but we removed categorization logic.
        # "Read a file" is in description, so "file" might be there.
        # But "Capability Summary" header should definitely be gone.

if __name__ == '__main__':
    unittest.main()
