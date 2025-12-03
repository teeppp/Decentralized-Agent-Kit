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
async def planner(task_description: str, plan_steps: list[str], allowed_tools: list[str] = []) -> str:
    """
    Create a plan and restrict future actions to specific tools (Ulysses Pact).
    Args:
        task_description: Description of the task to plan for.
        plan_steps: Ordered list of steps to accomplish the task.
        allowed_tools: List of tool names you intend to use (e.g. ["read_file", "run_command"]).
                       'planner', 'ask_question', 'attempt_answer' are always allowed.
    """
    plan_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(plan_steps)])
    
    restriction_msg = ""
    if allowed_tools:
        restriction_msg = f"\n\n[System] Ulysses Pact Active: You are now restricted to using only: {', '.join(allowed_tools)}"
    
    return f"Plan recorded for '{task_description}':\n{plan_str}{restriction_msg}"

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
