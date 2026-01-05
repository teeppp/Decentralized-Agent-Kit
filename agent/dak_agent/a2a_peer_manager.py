"""
A2A Peer Manager: Dynamically loads A2A peers from agent_config.yaml
Similar to MCP - config-based, not hardcoded.
"""
import os
import yaml
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Check if A2A dependencies are available
try:
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    logger.warning("RemoteA2aAgent not available. A2A peer functionality disabled.")


class A2APeerConfig:
    """Configuration for a single A2A peer."""
    def __init__(self, name: str, url: str, capabilities: List[str] = None):
        self.name = name
        self.url = url
        self.capabilities = capabilities or []
    
    def __repr__(self):
        return f"A2APeer({self.name}, {self.url}, caps={self.capabilities})"


def load_a2a_peers_from_config(config_path: str = None) -> List[A2APeerConfig]:
    """
    Load A2A peer configurations from agent_config.yaml.
    
    Returns:
        List of A2APeerConfig objects
    """
    if config_path is None:
        # Try multiple paths
        possible_paths = [
            "/app/agent_config.yaml",  # Docker container path (first priority)
            os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml"),
            "agent_config.yaml",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break
    
    if not config_path or not os.path.exists(config_path):
        logger.warning("agent_config.yaml not found. No A2A peers configured.")
        return []
    
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        peers = []
        for peer_config in config.get("a2a_peers", []):
            peer = A2APeerConfig(
                name=peer_config.get("name"),
                url=peer_config.get("url"),
                capabilities=peer_config.get("capabilities", [])
            )
            peers.append(peer)
            logger.info(f"Loaded A2A peer: {peer}")
        
        return peers
    except Exception as e:
        logger.error(f"Failed to load A2A config: {e}")
        return []


def create_remote_a2a_agents(peers: List[A2APeerConfig]) -> List["RemoteA2aAgent"]:
    """
    Create RemoteA2aAgent instances from peer configurations.
    
    Returns:
        List of RemoteA2aAgent instances
    """
    if not A2A_AVAILABLE:
        logger.warning("RemoteA2aAgent not available. Returning empty list.")
        return []
    
    agents = []
    for peer in peers:
        try:
            # Build description from capabilities
            caps_str = ", ".join(peer.capabilities) if peer.capabilities else "general purpose"
            description = f"Remote agent '{peer.name}' at {peer.url}. Capabilities: {caps_str}"
            
            # Create RemoteA2aAgent with agent_card URL
            # ADK uses `/a2a/{agent_name}/.well-known/agent-card.json` (per A2A SDK 0.2.6+)
            agent_card_url = peer.url.rstrip('/') + "/a2a/dak_agent/.well-known/agent-card.json"
            
            agent = RemoteA2aAgent(
                name=peer.name,
                agent_card=agent_card_url,
                description=description
            )
            agents.append(agent)
            logger.info(f"Created RemoteA2aAgent: {peer.name} -> {agent_card_url}")
        except Exception as e:
            logger.error(f"Failed to create RemoteA2aAgent for {peer.name}: {e}")
    
    return agents


def get_a2a_sub_agents() -> List["RemoteA2aAgent"]:
    """
    Main entry point: Load A2A peers from config and create agents.
    Call this from agent.py to get sub-agents.
    
    Set ENABLE_A2A_CONSUMER=true to enable A2A sub-agents (Consumer mode).
    Provider agents should not have this set to avoid infinite loops.
    """
    # Only enable A2A sub-agents if explicitly set (Consumer mode)
    if os.getenv("ENABLE_A2A_CONSUMER", "false").lower() != "true":
        logger.info("A2A Consumer mode disabled. No sub-agents loaded.")
        return []
    
    peers = load_a2a_peers_from_config()
    return create_remote_a2a_agents(peers)

