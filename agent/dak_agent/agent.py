from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
import os

# MCP Server configuration
mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")

from pydantic import ConfigDict

class PatchedMcpToolset(McpToolset):
    model_config = ConfigDict(arbitrary_types_allowed=True)

# Create MCP toolset
mcp_toolset = PatchedMcpToolset(
    connection_params=StreamableHTTPConnectionParams(url=mcp_url),
    require_confirmation=True
)

# Define the root agent
root_agent = LlmAgent(
    model='gemini-3-pro-preview',
    name='dak_agent',
    instruction='You are a helpful assistant powered by the Decentralized Agent Kit.',
    tools=[mcp_toolset],
)
