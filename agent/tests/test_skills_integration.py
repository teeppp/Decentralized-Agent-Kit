import pytest
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock

# Add agent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dak_agent.skill_registry import SkillRegistry
from google.adk.models import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import FunctionTool

# Mock McpToolset
class MockMcpToolset:
    def __init__(self, connection_params, tool_filter=None, require_confirmation=False):
        self.tool_filter = tool_filter
        self.name = "MockMcpToolset"
        self._tools = []
    
    async def get_tools(self):
        # Return mock tools
        mock_tool = MagicMock()
        mock_tool.name = "remote_tool_1"
        mock_tool.description = "Description 1"
        return [mock_tool]

class MockModel(BaseLlm):
    model: str = "gemini-2.5-flash"
    
    def prompt(self, prompt: str, **kwargs) -> LlmResponse:
        return LlmResponse(content="mock response")
        
    async def generate_content_async(self, prompt: str, **kwargs) -> LlmResponse:
        return LlmResponse(content="mock response")

@pytest.fixture
def mock_agent():
    with patch('google.adk.tools.mcp_tool.McpToolset', MockMcpToolset), \
         patch('dak_agent.adaptive_agent.McpToolset', MockMcpToolset), \
         patch('dak_agent.adaptive_agent.genai.Client') as MockGenAI:
        
        from dak_agent.adaptive_agent import AdaptiveAgent
        
        mock_model = MockModel()
        
        agent = AdaptiveAgent(
            model=mock_model,
            name="TestAgent",
            instruction="System Prompt",
            tools=[],
            mcp_url="http://mock-mcp"
        )
        
        # Mock skill registry
        agent.skill_registry = MagicMock(spec=SkillRegistry)
        agent.skill_registry.list_skills.return_value = [
            {'name': 'filesystem', 'description': 'Manage files and directories'}
        ]
        agent.skill_registry.get_skill.side_effect = lambda name: {
            'name': 'filesystem',
            'description': 'Manage files and directories',
            'tools': ['read_file', 'list_files'],
            'instructions': 'Use this skill to manage files.'
        } if name == 'filesystem' else None

        return agent

@pytest.mark.asyncio
async def test_list_skills(mock_agent):
    list_skills_tool = next(t for t in mock_agent.tools if t.name == 'list_skills')
    
    # Execute async function
    # Note: FunctionTool wraps the function. If we access .fn or .func (depending on version), we get the raw function.
    # In google-adk, FunctionTool stores the callable in ._fn usually, or we can call the tool itself?
    # Actually, FunctionTool is callable if it implements __call__, but usually we want the underlying function for unit testing.
    # Let's check how FunctionTool is implemented or just access the function passed to it.
    # In AdaptiveAgent, we did: FunctionTool(list_skills, ...)
    # So we can try to find where the callable is stored.
    # Usually it's `tool.fn` or `tool._fn`.
    
    # Assuming `tool.fn` is the callable (based on typical implementations)
    # If `tool.fn` is not available, we might need to inspect `tool`.
    
    # Let's assume we can call the tool directly if it's a FunctionTool instance?
    # Or access the underlying function.
    
    # For now, let's try to access the function. 
    # In the previous successful tests, we used `tool.func` or `tool.fn`.
    # Let's try `tool.fn` as per my previous edits.
    
    func = getattr(list_skills_tool, 'fn', getattr(list_skills_tool, 'func', None))
    if not func:
        # Fallback for some implementations
        func = list_skills_tool._fn
        
    result = await func()
    
    assert "filesystem" in result
    assert "Manage files and directories" in result

@pytest.mark.asyncio
async def test_enable_skill(mock_agent):
    enable_skill_tool = next(t for t in mock_agent.tools if t.name == 'enable_skill')
    func = getattr(enable_skill_tool, 'fn', getattr(enable_skill_tool, 'func', None))
    
    result = await func(skill_name="filesystem")
    
    assert "'filesystem' enabled." in result
    assert "# Skill: filesystem" in mock_agent.instruction
    
    # Verify toolset added
    mcp_toolsets = [t for t in mock_agent.tools if getattr(t, 'name', '') == 'MockMcpToolset']
    assert len(mcp_toolsets) > 0
    assert set(mcp_toolsets[-1].tool_filter) == {'read_file', 'list_files'}

@pytest.mark.asyncio
async def test_enable_nonexistent_skill(mock_agent):
    enable_skill_tool = next(t for t in mock_agent.tools if t.name == 'enable_skill')
    func = getattr(enable_skill_tool, 'fn', getattr(enable_skill_tool, 'func', None))
    
    result = await func(skill_name="fake-skill")
    
    assert "Error" in result
    assert "not found" in result

@pytest.mark.asyncio
async def test_zero_config_discovery(mock_agent):
    # 1. List Skills (triggers lazy load)
    list_skills_tool = next(t for t in mock_agent.tools if t.name == 'list_skills')
    func_list = getattr(list_skills_tool, 'fn', getattr(list_skills_tool, 'func', None))
    
    result = await func_list()
    
    # Verify remote tools are listed (MockMcpToolset returns remote_tool_1)
    assert "Individual Remote Tools" in result
    assert "remote_tool_1" in result
    
    # 2. Enable Remote Tool
    enable_skill_tool = next(t for t in mock_agent.tools if t.name == 'enable_skill')
    func_enable = getattr(enable_skill_tool, 'fn', getattr(enable_skill_tool, 'func', None))
    
    result = await func_enable(skill_name="remote_tool_1")
    
    assert "'remote_tool_1' enabled." in result
    assert "# Tool Enabled: remote_tool_1" in mock_agent.instruction
    
    # Verify toolset added with filter
    mcp_toolsets = [t for t in mock_agent.tools if getattr(t, 'name', '') == 'MockMcpToolset']
    # The last one should be the one for remote_tool_1
    assert mcp_toolsets[-1].tool_filter == ['remote_tool_1']
