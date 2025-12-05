import pytest
from unittest.mock import MagicMock, patch
from dak_agent.adaptive_agent import AdaptiveAgent
from dak_agent.mode_manager import ModeManager
from google.adk.agents import LlmAgent
from google.genai import types

class TestAdaptiveAgent:
    
    @pytest.fixture
    def mock_tools(self):
        tool1 = MagicMock()
        tool1.name = "tool1"
        tool2 = MagicMock()
        tool2.name = "tool2"
        return [tool1, tool2]

    @patch("dak_agent.adaptive_agent.genai.Client")
    def test_initialization(self, mock_genai_client, mock_tools):
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=mock_tools
        )
        
        assert agent.model == "test-model"
        assert agent.name == "test_agent"
        assert isinstance(agent._mode_manager, ModeManager)
        assert agent._meta_agent_client is not None

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    def test_initial_turn_trigger(self, mock_generate_config, mock_genai_client, mock_tools):
        """Test that the first turn always triggers a mode switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=mock_tools
        )
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [mock_tools[0]])
        
        # Simulate callback (first turn)
        context = MagicMock()
        context.session.contents = []
        agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)
        
        # Verify Switch happened
        assert agent.instruction.startswith("New Instruction")
        # In the new implementation, we keep all original tools + potentially add guidance
        # So the tool count should be at least the original count
        assert len(agent.tools) >= len(mock_tools)
        
        # Verify generate_mode_config called with client
        mock_generate_config.assert_called_once()
        args, kwargs = mock_generate_config.call_args
        assert args[2] == agent._meta_agent_client

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    def test_token_threshold_trigger(self, mock_generate_config, mock_genai_client, mock_tools):
        """Test that exceeding token threshold triggers a switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=mock_tools
        )
        
        # Bypass initial turn trigger
        agent._mode_manager._is_first_turn = False
        
        # Set a low max token count for testing
        agent._mode_manager.max_context_tokens = 100
        agent._mode_manager.token_threshold = 0.5 # 50 tokens
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [mock_tools[0]])
        
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
        
        agent._wrapped_callback(llm_response=MagicMock(), callback_context=context)
        
        # Verify Switch happened
        assert agent.instruction == "New Instruction"
        mock_generate_config.assert_called_once()

    @patch("dak_agent.adaptive_agent.genai.Client")
    @patch("dak_agent.mode_manager.ModeManager.generate_mode_config")
    def test_switch_mode_tool_trigger(self, mock_generate_config, mock_genai_client, mock_tools):
        """Test that LLM calling switch_mode triggers a switch."""
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="Initial instruction",
            tools=mock_tools
        )
        
        # Bypass initial turn trigger
        agent._mode_manager._is_first_turn = False
        
        # Mock generate_config
        mock_generate_config.return_value = ("New Instruction", [mock_tools[0]])
        
        # Create LLM response with switch_mode tool call
        llm_response = MagicMock()
        mock_part = MagicMock()
        mock_part.function_call = MagicMock()
        mock_part.function_call.name = "switch_mode"
        mock_part.function_call.args = {"reason": "test", "new_focus": "debugging"}
        llm_response.content.parts = [mock_part]
        
        context = MagicMock()
        context.session.contents = []
        
        agent._wrapped_callback(llm_response=llm_response, callback_context=context)
        
        # Verify Switch happened
        assert agent.instruction == "New Instruction"
        mock_generate_config.assert_called_once()
