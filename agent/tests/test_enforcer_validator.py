import unittest
from unittest.mock import MagicMock
from dak_agent.enforcer_validator import enforcer_validator, SessionState
from google.adk.models.llm_response import LlmResponse
from google.genai import types

# Marker used by enforcer to indicate blocked response
ENFORCER_BLOCKED_MARKER = "[ENFORCER_BLOCKED]"

class TestEnforcerValidator(unittest.TestCase):
    def setUp(self):
        self.callback_context = MagicMock()
        self.callback_context.session = MagicMock()
        self.callback_context.session.contents = []
        self.session_state = SessionState()

    def test_allow_tool_call(self):
        # Create a response with a function call
        response = LlmResponse(
            content=types.Content(
                parts=[
                    types.Part(function_call=types.FunctionCall(name="some_tool", args={}))
                ],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNone(result, "Should allow response with tool call")

    def test_switch_mode_allowed_in_plan(self):
        # Set a restrictive plan
        self.session_state.set_plan(["read_file"])
        
        # Try to call switch_mode
        response = LlmResponse(
            content=types.Content(
                parts=[
                    types.Part(function_call=types.FunctionCall(name="switch_mode", args={"reason": "test", "new_focus": "test"}))
                ],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNone(result, "Should allow switch_mode even if not explicitly in plan (it is a core tool)")

    def test_block_text_only_no_history(self):
        # Create a text-only response
        response = LlmResponse(
            content=types.Content(
                parts=[types.Part(text="Hello world")],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNotNone(result, "Should block text-only response")
        
        # Verify it returns a text-based enforcement error (not function call)
        self.assertTrue(result.content and result.content.parts, "Should have content")
        
        # Check for the ENFORCER_BLOCKED marker in text
        has_text_error = False
        for part in result.content.parts:
            if hasattr(part, 'text') and part.text:
                if ENFORCER_BLOCKED_MARKER in part.text:
                    has_text_error = True
                    self.assertIn("Direct responses are not allowed", part.text)
                    break
        
        self.assertTrue(has_text_error, "Should return text-based enforcement error with marker")

    def test_block_text_after_attempt_answer(self):
        # Mock history with attempt_answer response
        mock_content = MagicMock()
        mock_part = MagicMock()
        mock_part.function_response = MagicMock()
        mock_part.function_response.name = "attempt_answer"
        mock_content.parts = [mock_part]
        
        self.callback_context.session.contents = [mock_content]
        
        # Create a text-only response
        response = LlmResponse(
            content=types.Content(
                parts=[types.Part(text="Here is the answer")],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNotNone(result, "Should block text response - enforcer mode blocks all text")
        
        # Verify it returns a text-based enforcement error
        has_text_error = False
        for part in result.content.parts:
            if hasattr(part, 'text') and part.text and ENFORCER_BLOCKED_MARKER in part.text:
                has_text_error = True
                break
        self.assertTrue(has_text_error, "Should return text-based enforcement error")

    def test_block_text_after_ask_question(self):
        # Mock history with ask_question response
        mock_content = MagicMock()
        mock_part = MagicMock()
        mock_part.function_response = MagicMock()
        mock_part.function_response.name = "ask_question"
        mock_content.parts = [mock_part]
        
        self.callback_context.session.contents = [mock_content]
        
        # Create a text-only response
        response = LlmResponse(
            content=types.Content(
                parts=[types.Part(text="I have a question")],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNotNone(result, "Should block text response - enforcer mode blocks all text")
        
        # Verify it returns a text-based enforcement error
        has_text_error = False
        for part in result.content.parts:
            if hasattr(part, 'text') and part.text and ENFORCER_BLOCKED_MARKER in part.text:
                has_text_error = True
                break
        self.assertTrue(has_text_error, "Should return text-based enforcement error")

    def test_block_text_after_other_tool(self):
        # Mock history with some other tool response (e.g. read_file)
        mock_content = MagicMock()
        mock_part = MagicMock()
        mock_part.function_response = MagicMock()
        mock_part.function_response.name = "read_file"
        mock_content.parts = [mock_part]
        
        self.callback_context.session.contents = [mock_content]
        
        # Create a text-only response
        response = LlmResponse(
            content=types.Content(
                parts=[types.Part(text="I read the file")],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context, self.session_state)
        self.assertIsNotNone(result, "Should block text response after non-terminal tool")
        
        # Verify it returns a text-based enforcement error
        has_text_error = False
        for part in result.content.parts:
            if hasattr(part, 'text') and part.text and ENFORCER_BLOCKED_MARKER in part.text:
                has_text_error = True
                break
        self.assertTrue(has_text_error, "Should return text-based enforcement error")

if __name__ == '__main__':
    unittest.main()
