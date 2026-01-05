import pytest
from unittest.mock import MagicMock, patch
from dak_agent.adaptive_agent import AdaptiveAgent
from skills.symbol_wallet.paid_tool import PaymentRequiredError

class TestAp2Protocol:
    @pytest.fixture
    def agent(self):
        # Mock dependencies to avoid full initialization
        with patch('dak_agent.adaptive_agent.ModeManager'), \
             patch('dak_agent.adaptive_agent.SkillRegistry'), \
             patch('dak_agent.adaptive_agent.WalletManager'), \
             patch('dak_agent.adaptive_agent.McpToolset'):
            
            agent = AdaptiveAgent(model="test-model", name="test_agent", instruction="test-instruction", tools=[])
            # Manually set private attributes that would be set in __init__
            agent._enable_ap2 = True
            agent.tools = []
            return agent

    def test_payment_required_handling(self, agent):
        """Test that PaymentRequiredError triggers balance check and modifies error message."""
        # Setup the error
        error = PaymentRequiredError(price=10.0, address="TestAddress", message="Service fee")
        
        # Mock a tool that looks like check_solana_balance
        mock_balance_tool = MagicMock()
        mock_balance_tool.name = "check_solana_balance"
        mock_balance_tool.fn.return_value = "Mock Balance: 1000.0 SOL"
        
        # Add tool to agent
        agent.tools = [mock_balance_tool]
        
        # Call _on_tool_error
        result = agent._on_tool_error(tool=MagicMock(), args={}, tool_context=None, error=error)
        
        # Verify result
        assert "error" in result
        error_msg = result["error"]
        
        # Check that balance info was injected
        assert "Current Wallet Status" in error_msg
        assert "Mock Balance: 1000.0 SOL" in error_msg
        
        # Check that payment details are present
        assert "Amount**: 10.0" in error_msg
        assert "Recipient**: TestAddress" in error_msg
        
        # Verify balance tool was called
        mock_balance_tool.fn.assert_called_once()

    def test_payment_required_no_balance_tool(self, agent):
        """Test handling when check_solana_balance tool is missing."""
        error = PaymentRequiredError(price=10.0, address="TestAddress", message="Payment required")
        agent.tools = [] # No tools
        
        result = agent._on_tool_error(tool=MagicMock(), args={}, tool_context=None, error=error)
        
        assert "error" in result
        error_msg = result["error"]
        
        # Should still have payment info but no balance info
        assert "Amount**: 10.0" in error_msg
        assert "Current Wallet Status" not in error_msg
