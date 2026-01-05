import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dak_agent.adaptive_agent import AdaptiveAgent
from dak_agent.mode_manager import ModeManager
from google.adk.tools import FunctionTool

class TestAdaptiveAgent(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        self.tool1 = MagicMock()
        self.tool1.name = "tool1"
        self.tool2 = MagicMock()
        self.tool2.name = "tool2"
        self.mock_tools = [self.tool1, self.tool2]

    @patch("dak_agent.adaptive_agent.genai.Client")
    def test_initialization(self, mock_genai_client):
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
        self.assertIn("tool1", tool_names)
        self.assertIn("tool2", tool_names)
        self.assertEqual(agent.model, "test-model")
        self.assertEqual(agent.name, "test_agent")
        self.assertIsInstance(agent._mode_manager, ModeManager)
        self.assertIsNotNone(agent._meta_agent_client)

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_initial_turn_trigger(self, mock_generate_config, mock_genai_client):
        """Test that the first turn does NOT trigger a mode switch (starts with minimal tools)."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [self.mock_tools[0]], [])
        
        # Simulate callback (first turn)
        context = MagicMock()
        context.session.contents = []
        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)
        
        # Verify Switch DID NOT happen (instruction remains same)
        self.assertEqual(agent.instruction, "Initial instruction")
        
        # Verify generate_mode_config NOT called
        mock_generate_config.assert_not_called()
        
        # Verify _is_first_turn is set to False (it happens inside ModeManager.should_switch)
        # But wait, should_switch returns False on first turn and sets flag to False.
        # Let's verify the flag is False
        self.assertFalse(agent._mode_manager._is_first_turn)

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_token_threshold_trigger(self, mock_generate_config, mock_genai_client):
        """Test that exceeding token threshold triggers a switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        
        # Bypass initial turn trigger
        agent._mode_manager._is_first_turn = False
        
        # Set a low max token count for testing
        agent._mode_manager.max_context_tokens = 100
        agent._mode_manager.token_threshold = 0.5 # 50 tokens
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [self.mock_tools[0]], [])
        
        # Simulate callback with heavy context
        context = MagicMock()
        # Create content that exceeds threshold (approx 4 chars per token)
        # 60 tokens * 4 = 240 chars
        heavy_text = "a" * 240 
        mock_part = MagicMock()
        mock_part.text = heavy_text
        mock_content = MagicMock()
        mock_content.parts = [mock_part]
        context.session.contents = [mock_content]
        
        await agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)
        
        # Verify Switch happened
        self.assertEqual(agent.instruction, "New Instruction")
        mock_generate_config.assert_called_once()

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    async def test_switch_mode_tool_trigger(self, mock_generate_config, mock_genai_client):
        """Test that LLM calling switch_mode triggers a switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools
        )
        
        # Bypass initial turn trigger
        agent._mode_manager._is_first_turn = False
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [self.mock_tools[0]], [])
        
        # Create LLM response with switch_mode tool call
        llm_response = MagicMock()
        mock_part = MagicMock()
        mock_part.function_call = MagicMock()
        mock_part.function_call.name = "switch_mode"
        mock_part.function_call.args = {"reason": "test", "new_focus": "debugging"}
        llm_response.content.parts = [mock_part]
        
        context = MagicMock()
        context.session.contents = []
        
        await agent._wrapped_callback(llm_response=llm_response, callback_context=context)
        
        # Verify Switch happened
        self.assertEqual(agent.instruction, "New Instruction")
        mock_generate_config.assert_called_once()

if __name__ == '__main__':
    unittest.main()
