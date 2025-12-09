import contextlib
import os
import subprocess
import glob
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

# Initialize FastMCP server with recommended settings
mcp = FastMCP("dak-agent-mcp", json_response=True)

@mcp.tool()
async def deep_think(thought: str) -> str:
    """
    A tool for deep thinking and complex reasoning. 
    Use this when the user asks for a deep analysis or "deep think" on a topic.
    Returns a thought process.
    """
    return thought

@mcp.tool()
async def read_file(path: str) -> str:
    """
    Read the content of a file.
    Args:
        path: The path to the file to read (relative to /projects).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """
    Write content to a file. Overwrites existing content.
    Args:
        path: The path to the file to write.
        content: The content to write.
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

@mcp.tool()
async def list_files(path: str = ".") -> str:
    """
    List files and directories in a given path.
    Args:
        path: The directory path to list (default: current directory).
    """
    try:
        items = os.listdir(path)
        return "\n".join(items)
    except Exception as e:
        return f"Error listing files: {e}"

@mcp.tool()
async def run_command(command: str) -> str:
    """
    Execute a shell command.
    Args:
        command: The command to execute.
    """
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        output = f"Stdout:\n{result.stdout}\n"
        if result.stderr:
            output += f"\nStderr:\n{result.stderr}"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error executing command: {e}"

@mcp.tool()
async def search_files(pattern: str, path: str = ".") -> str:
    """
    Search for files matching a glob pattern.
    Args:
        pattern: The glob pattern to search for (e.g., "*.py").
        path: The root path to search in.
    """
    try:
        matches = []
        for root, _, files in os.walk(path):
            for file in files:
                if glob.fnmatch.fnmatch(file, pattern):
                    matches.append(os.path.join(root, file))
        return "\n".join(matches)
    except Exception as e:
        return f"Error searching files: {e}"

@mcp.tool()
async def list_available_tools() -> str:
    """
    List all available tools on this MCP server.
    Use this to discover what tools are available before requesting a mode switch.
    """
    tool_list = []
    # FastMCP stores tools in _tool_manager
    if hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        for name, tool_info in mcp._tool_manager._tools.items():
            description = tool_info.description if hasattr(tool_info, 'description') else "No description"
            tool_list.append(f"- {name}: {description}")
    else:
        # Fallback: try to get tools from mcp directly
        # FastMCP might expose tools differently in different versions
        tool_list.append("Unable to introspect tools. MCP server structure unknown.")
    
    return "AVAILABLE MCP TOOLS:\n" + "\n".join(tool_list)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # Switch to the projects directory to ensure tools operate on the user's workspace
    try:
        if os.path.exists("/projects"):
            os.chdir("/projects")
            print("Changed working directory to /projects")
        else:
            print("Warning: /projects directory not found. File tools may not work as expected.")
    except Exception as e:
        print(f"Error changing directory: {e}")

    async with contextlib.AsyncExitStack() as stack:
        # Initialize the FastMCP session manager
        await stack.enter_async_context(mcp.session_manager.run())
        yield

# Mount the StreamableHTTP server to a Starlette app
app = Starlette(
    routes=[
        Mount("/", app=mcp.streamable_http_app()),
    ],
    lifespan=lifespan
)

if __name__ == "__main__":
    # Run with uvicorn, binding to 0.0.0.0 for Docker access
    uvicorn.run(app, host="0.0.0.0", port=8000)
