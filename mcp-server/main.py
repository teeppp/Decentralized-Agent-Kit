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

# Output bounds: an unbounded tool result (a whole file, a recursive listing)
# can overflow the calling model's context window in one call. Tools return at
# most this much and tell the caller how to fetch the rest.
def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment; a bad value must not crash the server."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError
        return value
    except ValueError:
        print(f"Warning: ignoring invalid {name}={raw!r}; using {default}.")
        return default


MAX_OUTPUT_CHARS = _env_int("MCP_MAX_OUTPUT_CHARS", 50000)
MAX_LIST_ENTRIES = _env_int("MCP_MAX_LIST_ENTRIES", 500)


def _cap_text(text: str, hint: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[truncated: {len(text) - limit} more chars. {hint}]"


def _cap_entries(entries: list, hint: str, limit: int = MAX_LIST_ENTRIES) -> str:
    if len(entries) <= limit:
        return "\n".join(entries)
    shown = "\n".join(entries[:limit])
    return f"{shown}\n\n[truncated: {len(entries) - limit} more entries. {hint}]"


@mcp.tool()
async def deep_think(thought: str) -> str:
    """
    A tool for deep thinking and complex reasoning. 
    Use this when the user asks for a deep analysis or "deep think" on a topic.
    Returns a thought process.
    """
    return thought

@mcp.tool()
async def read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    """
    Read the content of a file. For large files, read a range of lines.
    Args:
        path: The path to the file to read (relative to /projects).
        offset: 0-based line number to start reading from (default: 0).
        limit: Maximum number of lines to return (default: 0 = to the end of the file).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return f"Error reading file: {e}"
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    if offset > 0 or limit > 0:
        start = max(0, offset)
        end = start + limit if limit > 0 else total_lines
        content = "".join(lines[start:end])
    return _cap_text(
        content,
        f"The file has {total_lines} lines; call read_file(path, offset=<line>, limit=<lines>) to read a range.",
    )

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
        items = sorted(os.listdir(path))
        return _cap_entries(items, "List a subdirectory or use search_files with a pattern.")
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
        # Cap each stream on its own: capping the concatenation would drop the
        # stderr of a command that wrote a lot to stdout before failing.
        hint = "Narrow the command output (e.g. pipe through head, tail or grep)."
        output = f"Exit code: {result.returncode}\nStdout:\n{_cap_text(result.stdout, hint)}\n"
        if result.stderr:
            output += f"\nStderr:\n{_cap_text(result.stderr, hint)}"
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
        return _cap_entries(matches, "Use a more specific pattern or path.")
    except Exception as e:
        return f"Error searching files: {e}"






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
