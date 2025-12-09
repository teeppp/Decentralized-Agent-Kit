import pytest
import asyncio
from unittest.mock import MagicMock, patch
from dak_agent.adaptive_agent import AdaptiveAgent
from google.adk.tools import FunctionTool
from mcp.server.fastmcp import FastMCP

# We need to test the interaction between AdaptiveAgent and a real/mocked MCP server
# Since spinning up a real server in unit tests is complex, we will mock the McpToolset response
# but ensure the AdaptiveAgent logic correctly handles it.

@pytest.mark.asyncio
async def test_list_available_tools_integration():
    """
    Test that list_available_tools correctly fetches tools from a mocked MCP connection.
    This simulates the full flow within the agent without requiring a running HTTP server.
    """
    # Mock the McpToolset to return a specific list of tools
    mock_tool1 = MagicMock()
    mock_tool1.name = "mock_tool_1"
    mock_tool1.description = "Description for mock tool 1"
    
    mock_tool2 = MagicMock()
    mock_tool2.name = "mock_tool_2"
    mock_tool2.description = "Description for mock tool 2"
    
    mock_tools_list = [mock_tool1, mock_tool2]
    
    # Patch McpToolset inside adaptive_agent.py
    with patch("dak_agent.adaptive_agent.McpToolset") as MockMcpToolset:
        # Configure the mock to return our tools
        mock_toolset_instance = MockMcpToolset.return_value
        
        # Create a future for the async result
        future = asyncio.Future()
        future.set_result(mock_tools_list)
        mock_toolset_instance.get_tools.return_value = future
        
        # Initialize agent
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="instruction",
            tools=[],
            mcp_url="http://mock-mcp:8000"
        )
        
        # Call list_available_tools
        result = await agent.list_available_tools()
        
        # Verify result
        assert "AVAILABLE MCP TOOLS:" in result
        assert "- mock_tool_1: Description for mock tool 1" in result
        assert "- mock_tool_2: Description for mock tool 2" in result
        
        # Verify McpToolset was initialized with correct URL
        MockMcpToolset.assert_called()
        call_args = MockMcpToolset.call_args
        assert call_args.kwargs['connection_params'].url == "http://mock-mcp:8000"

@pytest.mark.asyncio
async def test_list_available_tools_empty():
    """Test handling of empty tool list."""
    with patch("dak_agent.adaptive_agent.McpToolset") as MockMcpToolset:
        mock_toolset_instance = MockMcpToolset.return_value
        
        future = asyncio.Future()
        future.set_result([])
        mock_toolset_instance.get_tools.return_value = future
        
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="instruction",
            tools=[],
            mcp_url="http://mock-mcp:8000"
        )
        
        result = await agent.list_available_tools()
        assert "No tools found on the MCP server" in result

@pytest.mark.asyncio
async def test_list_available_tools_error():
    """Test handling of connection error."""
    with patch("dak_agent.adaptive_agent.McpToolset") as MockMcpToolset:
        mock_toolset_instance = MockMcpToolset.return_value
        mock_toolset_instance.get_tools.side_effect = Exception("Connection refused")
        
        agent = AdaptiveAgent(
            model="test-model",
            name="test_agent",
            instruction="instruction",
            tools=[],
            mcp_url="http://mock-mcp:8000"
        )
        
        result = await agent.list_available_tools()
        assert "Error listing tools from MCP server" in result
        assert "Connection refused" in result
