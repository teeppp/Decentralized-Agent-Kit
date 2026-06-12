"""Central loading of agent_config.yaml (MCP servers and A2A peers)."""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_AGENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Candidate locations, in priority order: Docker image, repo checkout, CWD.
CONFIG_CANDIDATES = [
    "/app/agent_config.yaml",
    os.path.join(_AGENT_ROOT, "agent_config.yaml"),
    "agent_config.yaml",
]


@dataclass
class AgentConfig:
    """Parsed agent_config.yaml content."""
    mcp_servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    a2a_peers: List[Dict[str, Any]] = field(default_factory=list)


def find_config_path(path: Optional[str] = None) -> Optional[str]:
    candidates = [path] if path else CONFIG_CANDIDATES
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def load_agent_config(path: Optional[str] = None) -> AgentConfig:
    config_path = find_config_path(path)
    if not config_path:
        logger.warning("agent_config.yaml not found; using empty config.")
        return AgentConfig()

    try:
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load agent config from {config_path}: {e}")
        return AgentConfig()

    mcp_servers = {
        srv["name"]: srv for srv in raw.get("mcp_servers") or [] if isinstance(srv, dict) and "name" in srv
    }
    a2a_peers = [peer for peer in raw.get("a2a_peers") or [] if isinstance(peer, dict)]

    logger.info(
        f"Loaded agent config from {config_path}: "
        f"{len(mcp_servers)} MCP server(s), {len(a2a_peers)} A2A peer(s)"
    )
    return AgentConfig(mcp_servers=mcp_servers, a2a_peers=a2a_peers)


def get_litellm_model_name(model_name: str) -> str:
    """Prefix bare Gemini model names so LiteLLM uses Google AI Studio (API key) instead of Vertex AI."""
    if "gemini" in model_name and not model_name.startswith("gemini/"):
        return f"gemini/{model_name}"
    return model_name
