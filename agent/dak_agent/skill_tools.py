"""Client-side skill tools (list_skills / enable_skill) and skill tool loaders.

`make_skill_tools(agent)` returns the two FunctionTools the agent always
exposes; the heavy lifting lives in module-level functions so it can be
unit-tested without a full agent.
"""
import importlib.util
import logging
import os
import sys
from typing import Iterable, List, Optional, Tuple

from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

logger = logging.getLogger(__name__)

# Wallet tools auto-enabled alongside paid-service skills when AP2 is active,
# so the LLM can always check its balance and pay.
WALLET_TOOL_NAMES = ["check_solana_balance", "get_solana_address", "send_sol_payment"]

# Full wallet toolset exposed at the root agent when AP2 is enabled.
ALL_WALLET_TOOL_NAMES = WALLET_TOOL_NAMES + ["verify_sol_payment"]

_SOLANA_WALLET_TOOLS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "skills", "solana_wallet", "tools.py"
)


def _invalidate_canonical_tools_cache(tool_context) -> None:
    """Clear google-adk v2's per-invocation tool cache so mid-run tool additions
    (enable_skill) are visible on the next turn of the same run. No-op on v1 or
    when the context is unavailable."""
    try:
        tool_context._invocation_context.canonical_tools_cache = None
    except Exception:
        pass


def _sync_to_live_agent(tool_context, source_agent) -> None:
    """google-adk v2 executes each invocation on a per-run *copy* of the agent, so
    mutations to the root agent are invisible to the running invocation. Share the
    updated tools/instruction/active_skills onto the live invocation agent so tools
    enabled mid-run are callable in the same run. No-op on v1 / without context."""
    try:
        live = tool_context._invocation_context.agent
    except Exception:
        return
    if live is None or live is source_agent:
        return
    try:
        live.tools = source_agent.tools
        live.instruction = source_agent.instruction
        if hasattr(source_agent, "active_skills"):
            live.active_skills = source_agent.active_skills
    except Exception as e:
        logger.warning("Could not sync enabled skill to live agent: %s", e)


def _import_module_from_path(module_name: str, file_path: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_local_tools_from_skill(
    skill_name: str,
    skill_dir: str,
    required_tools: Iterable[str],
    current_tool_names: Iterable[str],
) -> Tuple[List[FunctionTool], List[str]]:
    """Load a skill's tools from its local tools.py.

    Returns (loaded FunctionTools, tool names that must fall back to MCP).
    """
    current = set(current_tool_names)
    missing = [name for name in required_tools if name not in current]

    tools_file = os.path.join(skill_dir, "tools.py")
    if not os.path.exists(tools_file):
        return [], missing

    try:
        module = _import_module_from_path(f"skills.{skill_name}.tools", tools_file)
    except Exception as e:
        logger.error(f"Failed to load local tools for {skill_name}: {e}")
        return [], missing

    local_tools: List[FunctionTool] = []
    mcp_fallback: List[str] = []
    for tool_name in missing:
        func = getattr(module, tool_name, None)
        if callable(func):
            # require_confirmation=False allows autonomous execution and the AP2 flow
            local_tools.append(FunctionTool(func, require_confirmation=False))
            logger.info(f"Loaded local tool '{tool_name}' from {skill_name}")
        else:
            if func is not None:
                logger.warning(f"'{tool_name}' in {skill_name} is not callable.")
            mcp_fallback.append(tool_name)
    return local_tools, mcp_fallback


def make_mcp_toolset(
    url: str,
    conn_type: str = "http",
    tool_filter: Optional[List[str]] = None,
) -> McpToolset:
    """Create an McpToolset for the given server URL and connection type."""
    if conn_type == "sse":
        from google.adk.tools.mcp_tool import SseConnectionParams
        conn_params = SseConnectionParams(url=url)
    else:
        conn_params = StreamableHTTPConnectionParams(url=url)
    return McpToolset(
        connection_params=conn_params,
        tool_filter=tool_filter,
        require_confirmation=False,
    )


def load_solana_wallet_tools(
    existing_tool_names: Iterable[str] = (),
    tool_names: Iterable[str] = WALLET_TOOL_NAMES,
) -> List[FunctionTool]:
    """Load the Solana wallet FunctionTools (for AP2), skipping already-present ones."""
    if not os.path.exists(_SOLANA_WALLET_TOOLS_FILE):
        logger.warning(f"Solana wallet tools not found at {_SOLANA_WALLET_TOOLS_FILE}")
        return []

    try:
        module = _import_module_from_path("skills.solana_wallet.tools", _SOLANA_WALLET_TOOLS_FILE)
    except Exception as e:
        logger.warning(f"Could not load Solana wallet tools: {e}")
        return []

    existing = set(existing_tool_names)
    tools = []
    for name in tool_names:
        if name in existing:
            continue
        func = getattr(module, name, None)
        if callable(func):
            tools.append(FunctionTool(func, require_confirmation=False))
            logger.info(f"Auto-added Solana wallet tool '{name}' for AP2 support")
    return tools


def make_skill_tools(agent) -> List[FunctionTool]:
    """Create the list_skills / enable_skill tools bound to an AdaptiveAgent.

    Thin closures over `agent`: ADK introspects the function signature to build
    the tool schema, so we cannot use bound methods with a `self` parameter.
    """

    async def list_skills() -> str:
        """
        List all available Agent Skills and Remote Tools.
        Returns a list of skills and tools with their names and descriptions.
        """
        await agent.ensure_remote_tools_loaded()

        output = []

        # 1. Local (curated) skills
        if agent.skill_registry:
            skills = agent.skill_registry.list_skills()
            if skills:
                output.append("## Curated Skills (Recommended)")
                output.extend([f"- {s['name']}: {s['description']}" for s in skills])

        # 2. Remote tools (zero-config)
        if agent.available_remote_tools:
            output.append("\n## Individual Remote Tools")
            output.extend([f"- {name}: {desc}" for name, desc in agent.available_remote_tools.items()])

        if not output:
            return "No skills or tools available."

        return "\n".join(output)

    async def enable_skill(skill_name: str, tool_context=None) -> str:
        """
        Enable a specific skill OR an individual remote tool.
        This loads the instructions and makes the tools available.
        """
        await agent.ensure_remote_tools_loaded()

        skill = agent.skill_registry.get_skill(skill_name) if agent.skill_registry else None

        if skill:
            if skill_name in agent.active_skills:
                return f"Skill '{skill_name}' is already active."
        elif skill_name in agent.available_remote_tools:
            if skill_name in agent.active_skills:
                return f"Tool '{skill_name}' is already active."
        else:
            return f"Error: Skill or Tool '{skill_name}' not found."

        agent.active_skills.append(skill_name)

        current_tool_names = {getattr(t, "name", None) for t in agent.tools} - {None}

        if skill:
            instructions = skill.get("instructions")
            if instructions:
                agent.instruction += f"\n\n# Skill: {skill_name}\n{instructions}"

            skill_dir = agent.skill_registry.find_skill_dir(skill_name)
            if not skill_dir:
                logger.warning(f"Skill directory for {skill_name} not found in any configured paths.")
                return f"Error: Skill directory for {skill_name} not found."

            local_tools, mcp_tool_names = load_local_tools_from_skill(
                skill_name, skill_dir, skill.get("tools", []), current_tool_names
            )
            if local_tools:
                agent.tools.extend(local_tools)
        else:
            # Zero-config remote tool: comes straight from MCP
            agent.instruction += (
                f"\n\n# Tool Enabled: {skill_name}\n"
                f"You have enabled the raw tool '{skill_name}'. Use it according to its schema."
            )
            mcp_tool_names = [skill_name] if skill_name not in current_tool_names else []

        if mcp_tool_names:
            # A skill may target a specific MCP server from agent_config.yaml;
            # otherwise use the default server.
            server_cfg = None
            if skill and skill.get("mcp_server"):
                server_cfg = agent.mcp_servers.get(skill["mcp_server"])
                if server_cfg:
                    logger.info(
                        f"Skill '{skill_name}' uses MCP server '{skill['mcp_server']}' "
                        f"at {server_cfg.get('url')} ({server_cfg.get('type', 'http')})"
                    )

            target_url = server_cfg.get("url") if server_cfg else agent.mcp_url
            target_type = server_cfg.get("type", "http") if server_cfg else "http"

            if target_url:
                try:
                    toolset = make_mcp_toolset(target_url, target_type, mcp_tool_names)
                    agent.tools.append(toolset)
                    logger.info(f"Added filtered McpToolset for tools: {mcp_tool_names} via {target_url}")
                except Exception as e:
                    logger.error(f"Failed to create McpToolset for {skill_name}: {e}")
                    return f"Error enabling {skill_name}: Failed to connect to tools. {e}"

        # AP2: make sure wallet tools are available alongside any paid-service skill
        if agent.ap2_enabled and skill_name != "solana_wallet" and "solana_wallet" not in agent.active_skills:
            existing = {getattr(t, "name", None) for t in agent.tools} - {None}
            agent.tools.extend(load_solana_wallet_tools(existing))

        # google-adk v2 runs each invocation on a *copy* of the agent, so the
        # mutations above (on the closure/root agent) are invisible to the current
        # run. Mirror the updated tools/instruction/active_skills onto the live
        # invocation agent (sharing the same objects) so the just-enabled tools are
        # callable within this same run, and invalidate the per-invocation tool cache.
        _sync_to_live_agent(tool_context, agent)
        _invalidate_canonical_tools_cache(tool_context)

        return f"'{skill_name}' enabled."

    return [
        FunctionTool(list_skills, require_confirmation=False),
        FunctionTool(enable_skill, require_confirmation=False),
    ]
