from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
try:
    t = McpToolset(connection_params=StreamableHTTPConnectionParams(url="http://localhost"), require_confirmation=False)
    t.tool_filter = ["a"]
    print("Mutable")
except Exception as e:
    print(f"Immutable: {e}")
