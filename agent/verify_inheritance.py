from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.mcp_tool import McpToolset
print(f"BaseToolset: {BaseToolset}")
print(f"McpToolset bases: {McpToolset.__bases__}")

from google.adk.tools.base_tool import BaseTool
print(f"BaseToolset inherits BaseTool: {issubclass(BaseToolset, BaseTool)}")
