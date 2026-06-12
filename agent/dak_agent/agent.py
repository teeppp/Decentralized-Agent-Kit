"""Root agent assembly: feature flags + tool wiring for `adk web`."""
import logging
import os

logger = logging.getLogger(__name__)

from .patches import apply_patches, setup_telemetry

apply_patches()
setup_telemetry()

from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from pydantic import ConfigDict

from .a2a_peer_manager import get_a2a_sub_agents
from .adaptive_agent import AdaptiveAgent
from .builtin_tools import make_builtin_tools
from .config import get_litellm_model_name
from .enforcer import ENFORCER_INSTRUCTION, enforcer_validator
from .skill_tools import ALL_WALLET_TOOL_NAMES, load_solana_wallet_tools


class PatchedMcpToolset(McpToolset):
    model_config = ConfigDict(arbitrary_types_allowed=True)


# --- MCP server (default) ---
mcp_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")
mcp_toolset = PatchedMcpToolset(
    connection_params=StreamableHTTPConnectionParams(url=mcp_url),
    require_confirmation=True,
)

# --- Feature flags ---
enforcer_mode = os.getenv("ENABLE_ENFORCER_MODE", "false").lower() == "true"
ap2_enabled = os.getenv("ENABLE_AP2_PROTOCOL", "false").lower() == "true"

# --- Tools ---
root_agent_tools = [mcp_toolset] + make_builtin_tools(enforcer_mode)

if ap2_enabled:
    wallet_tools = load_solana_wallet_tools(tool_names=ALL_WALLET_TOOL_NAMES)
    root_agent_tools.extend(wallet_tools)
    logger.info(f"Added {len(wallet_tools)} Solana wallet tools to root agent")

# --- Instruction & callbacks ---
if enforcer_mode:
    instruction = ENFORCER_INSTRUCTION
    after_model_callback = enforcer_validator
else:
    instruction = os.getenv(
        "AGENT_INSTRUCTION",
        "You are a helpful assistant powered by the Decentralized Agent Kit.",
    )
    after_model_callback = None

# --- Model ---
model_name = os.getenv("MODEL_NAME", os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"))
formatted_model_name = get_litellm_model_name(model_name)

# --- A2A sub-agents (Consumer mode) ---
a2a_sub_agents = get_a2a_sub_agents()
if a2a_sub_agents:
    logger.info(f"Loaded {len(a2a_sub_agents)} A2A peer agent(s)")

# --- Skill directories (colon-separated) ---
skills_dirs_env = os.getenv("AGENT_SKILLS_DIRS")
skills_dirs = None
if skills_dirs_env:
    skills_dirs = [d.strip() for d in skills_dirs_env.split(":") if d.strip()]
    logger.info(f"Configured skill directories: {skills_dirs}")

root_agent = AdaptiveAgent(
    model=LiteLlm(model=formatted_model_name),
    name="dak_agent",
    instruction=instruction,
    tools=root_agent_tools,
    sub_agents=a2a_sub_agents if a2a_sub_agents else None,
    after_model_callback=after_model_callback,
    mcp_url=mcp_url,
    skills_dirs=skills_dirs,
)
