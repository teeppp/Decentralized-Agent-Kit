import unittest
from unittest.mock import MagicMock
from dak_agent.enforcer_validator import enforcer_validator
from google.adk.models.llm_response import LlmResponse
from google.genai import types

class TestEnforcerValidator(unittest.TestCase):
    def setUp(self):
        self.callback_context = MagicMock()
        self.callback_context.session = MagicMock()
        self.callback_context.session.contents = []

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
        
        result = enforcer_validator(response, self.callback_context)
        self.assertIsNone(result, "Should allow response with tool call")

    def test_block_text_only_no_history(self):
        # Create a text-only response
        response = LlmResponse(
            content=types.Content(
                parts=[types.Part(text="Hello world")],
                role="model"
            )
        )
        
        result = enforcer_validator(response, self.callback_context)
        self.assertIsNotNone(result, "Should block text-only response")
        
        # Verify it returns a system_retry function call
        part = result.content.parts[0]
        self.assertTrue(hasattr(part, 'function_call'), "Should return a function call")
        self.assertEqual(part.function_call.name, "system_retry", "Should call system_retry")
        self.assertIn("Direct responses are not allowed", part.function_call.args['error_message'])

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
        
        result = enforcer_validator(response, self.callback_context)
        self.assertIsNotNone(result, "Should block text response - enforcer mode blocks all text")
        
        # Verify it returns a system_retry function call
        part = result.content.parts[0]
        self.assertTrue(hasattr(part, 'function_call'), "Should return a function call")
        self.assertEqual(part.function_call.name, "system_retry", "Should call system_retry")

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
        
        result = enforcer_validator(response, self.callback_context)
        self.assertIsNotNone(result, "Should block text response - enforcer mode blocks all text")
        
        # Verify it returns a system_retry function call
        part = result.content.parts[0]
        self.assertTrue(hasattr(part, 'function_call'), "Should return a function call")
        self.assertEqual(part.function_call.name, "system_retry", "Should call system_retry")

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
        
        result = enforcer_validator(response, self.callback_context)
        self.assertIsNotNone(result, "Should block text response after non-terminal tool")
        
        # Verify it returns a system_retry function call
        part = result.content.parts[0]
        self.assertTrue(hasattr(part, 'function_call'), "Should return a function call")
        self.assertEqual(part.function_call.name, "system_retry", "Should call system_retry")

if __name__ == '__main__':
    unittest.main()
