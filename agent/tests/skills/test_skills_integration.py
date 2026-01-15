import pytest
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock

# Add agent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))

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
        # Add skills_dirs attribute (list instead of single dir)
        agent.skill_registry.skills_dirs = ["/tmp/mock_skills"]
        
        agent.skill_registry.list_skills.return_value = [
            {'name': 'filesystem', 'description': 'Manage files and directories'}
        ]
        agent.skill_registry.get_skill.side_effect = lambda name: {
            'name': 'filesystem',
            'description': 'Manage files and directories',
            'tools': ['read_file', 'list_files'],
            'instructions': 'Use this skill to manage files.'
        } if name == 'filesystem' else None

        yield agent

@pytest.mark.asyncio
async def test_list_skills(mock_agent):
    list_skills_tool = next(t for t in mock_agent.tools if t.name == 'list_skills')
    
    func = getattr(list_skills_tool, 'fn', getattr(list_skills_tool, 'func', None))
    if not func:
        func = list_skills_tool._fn
        
    result = await func()
    
    assert "filesystem" in result
    assert "Manage files and directories" in result

@pytest.mark.asyncio
async def test_enable_skill(mock_agent):
    enable_skill_tool = next(t for t in mock_agent.tools if t.name == 'enable_skill')
    func = getattr(enable_skill_tool, 'fn', getattr(enable_skill_tool, 'func', None))
    
    # Mock os.path.exists to return True for skill dir, False for tools.py
    def mock_exists(path):
        # Return True for skill directories, False for tools.py
        if path.endswith("tools.py"):
            return False
        return True  # Skill directory exists
    
    with patch('dak_agent.adaptive_agent.os.path.exists', side_effect=mock_exists):
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
