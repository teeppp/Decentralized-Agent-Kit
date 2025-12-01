# MCP Server

A Model Context Protocol (MCP) server that provides tools for the Decentralized Agent Kit (DAK) agent.

## Overview

This MCP server exposes tools that can be discovered and used by the DAK agent through the MCP protocol. It uses the FastMCP framework with streamable HTTP transport for production-ready scalability.

## Available Tools

### `deep_think`

A tool for deep thinking and complex reasoning.

**Parameters:**
- `thought` (string, required): The thought or topic to analyze

**Returns:**
- The input thought as-is (echo functionality)

**Example Usage:**
```python
# Via MCP Client
result = await mcp_client.call_tool("deep_think", {"thought": "What is consciousness?"})
# Returns: "What is consciousness?"
```

## Architecture

- **Framework**: FastMCP with `json_response=True` for JSON responses
- **Transport**: Streamable HTTP (recommended for production)
- **Network**: Binds to `0.0.0.0:8000` via Uvicorn for Docker network access
- **Session Management**: Stateful sessions with proper lifecycle handling

## Adding New Tools

To add a new tool to the MCP server:

1. Define the tool function with the `@mcp.tool()` decorator:

```python
@mcp.tool()
async def my_new_tool(param1: str, param2: int) -> str:
    """
    Brief description of what this tool does.
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2
    
    Returns:
        Description of return value
    """
    # Your tool logic here
    return f"Processed {param1} with {param2}"
```

2. Rebuild the mcp-server container:

```bash
docker compose up --build -d mcp-server
```

3. The tool will automatically be discovered by the agent's MCP client.

## Development

### Running Locally

```bash
cd mcp-server
uv sync
uv run python main.py
```

### Testing with MCP Inspector

You can test the MCP server using the MCP Inspector tool:

```bash
npx @modelcontextprotocol/inspector
```

Then connect to `http://localhost:8000/mcp`.

## Configuration

The server is configured in `main.py`:

- **Host**: `0.0.0.0` (accessible from Docker network)
- **Port**: `8000` (mapped to host port `8001` in docker-compose)
- **Transport**: `streamable-http`
- **Session Mode**: Stateful (for clean session lifecycle)

## Dependencies

Managed via `uv` and defined in `pyproject.toml`:

- `mcp>=1.22.0`: MCP protocol implementation
- `httpx>=0.28.1`: HTTP client
- `uvicorn>=0.30.0`: ASGI server
- `starlette>=0.37.0`: Web framework

## Logs

Monitor server logs:

```bash
docker compose logs mcp-server -f
```

Expected log output for successful tool execution:

```
INFO:     Started server process [N]
StreamableHTTP session manager started
Created new transport with session ID: <session-id>
Processing request of type CallToolRequest
INFO:     172.x.x.x:xxxxx - "POST /mcp HTTP/1.1" 200 OK
Terminating session: <session-id>
INFO:     172.x.x.x:xxxxx - "DELETE /mcp HTTP/1.1" 200 OK
```
