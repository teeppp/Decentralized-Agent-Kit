import pytest
from unittest.mock import MagicMock, patch
from dak_agent.adaptive_agent import AdaptiveAgent
from dak_agent.mode_manager import ModeManager
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import FunctionTool

class TestAdaptiveAgentRefinement:
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_tools = [MagicMock(spec=FunctionTool)]
        self.mock_tools[0].name = "test_tool"
        self.agent = AdaptiveAgent(
            model="gemini-2.5-flash",
            name="test_agent",
            instruction="Initial instruction",
            tools=self.mock_tools,
            disable_mode_switching=False
        )
        # Mock Meta-Agent client
        self.agent._meta_agent_client = MagicMock()
        
    @patch('dak_agent.mode_manager.ModeManager.generate_mode_config')
    @pytest.mark.asyncio
    async def test_history_clearing_on_switch(self, mock_generate_config):
        # Setup mock return for generate_mode_config
        mock_generate_config.return_value = ("New Instruction", ["test_tool"])
        
        # Setup mock context with session history
        mock_context = MagicMock(spec=CallbackContext)
        mock_context.session = MagicMock()
        # Mock contents as a MagicMock that behaves like a list but tracks calls
        mock_contents = MagicMock(spec=list)
        mock_contents.__iter__.return_value = ["Old Message 1", "Old Message 2"]
        mock_context.session.contents = mock_contents
        
        # Trigger switch manually via internal method for testing
        # We need to mock _extract_history_summary as well
        with patch.object(self.agent, '_extract_history_summary', return_value="Summary"):
            await self.agent._perform_mode_switch(mock_context)
            
        # Verify instruction updated
        assert self.agent.instruction == "New Instruction"
        
        # Verify history cleared
        # Note: In the actual code we check if it's a list and clear it
        # Here we verify the clear method was called on the mock list
        mock_context.session.contents.clear.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_switch_mode_tool_preservation(self):
        # Ensure switch_mode is in builtin tools
        builtin_names = [t.name for t in self.agent._builtin_tools if hasattr(t, 'name')]
        # Note: In the test setup we passed a generic mock tool, so switch_mode might not be there unless we add it
        # But let's check if the logic in _perform_mode_switch preserves whatever is in _builtin_tools
        
        # Add a mock switch_mode tool to builtins
        mock_switch = MagicMock()
        mock_switch.name = "switch_mode"
        self.agent._builtin_tools.append(mock_switch)
        
        mock_context = MagicMock(spec=CallbackContext)
        mock_context.session.contents = []
        
        with patch.object(self.agent, '_extract_history_summary', return_value="Summary"), \
             patch('dak_agent.mode_manager.ModeManager.generate_mode_config', return_value=("New", ["other_tool"])):
            
            await self.agent._perform_mode_switch(mock_context)
            
            # Check if switch_mode is in the new tools list
            new_tool_names = [t.name for t in self.agent.tools if hasattr(t, 'name')]
            assert "switch_mode" in new_tool_names
