"""AdaptiveAgent: an LlmAgent with Dynamic Mode Switching and Agent Skills."""
import logging
import os
from typing import Any, Dict, List, Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from pydantic import ConfigDict, Field, PrivateAttr
import inspect

from . import remote_tools, skill_tools
from .config import load_agent_config
from .errors import PaymentRequiredError
from .handlers.payment_handler import PaymentHandler
from .mode_manager import ModeManager
from .skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


class AdaptiveAgent(LlmAgent):
    """
    A wrapper around LlmAgent that implements Dynamic Mode Switching and Agent Skills.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Override tools field to allow toolset instances
    tools: List[Any] = []

    skill_registry: Optional[SkillRegistry] = Field(default=None, exclude=True)
    available_remote_tools: Dict[str, str] = Field(default_factory=dict, exclude=True)

    _mode_manager: ModeManager = PrivateAttr()
    _all_available_tools: List[Any] = PrivateAttr()
    _builtin_tools: List[Any] = PrivateAttr()  # FunctionTools that never get filtered
    _original_callback: Optional[Any] = PrivateAttr(default=None)
    _disable_mode_switching: bool = PrivateAttr(default=False)
    _mcp_url: str = PrivateAttr(default="")
    _mcp_servers: Dict[str, Dict] = PrivateAttr(default_factory=dict)
    _active_skills: List[str] = PrivateAttr(default=[])
    _payment_handler: Optional[PaymentHandler] = PrivateAttr(default=None)
    _enable_ap2: bool = PrivateAttr(default=False)

    def __init__(
        self,
        model: str,
        name: str,
        instruction: str,
        tools: List[Any],
        sub_agents: Optional[List[Any]] = None,
        after_model_callback: Optional[Any] = None,
        disable_mode_switching: bool = False,
        mcp_url: Optional[str] = None,
        skills_dirs: Optional[List[str]] = None,
    ):
        # Split provided tools into built-in FunctionTools and MCP toolsets.
        # The agent starts with ONLY built-in tools; MCP tools are enabled via
        # skills or mode switching to keep the initial context small.
        all_tools = list(tools) + skill_tools.make_skill_tools(self)

        builtin_tools = []
        for tool in all_tools:
            if "Toolset" not in type(tool).__name__:
                builtin_tools.append(tool)
        logger.info("Initializing with minimal toolset (Client-Side Skills + Built-in)")

        init_kwargs = {
            "model": model,
            "name": name,
            "instruction": instruction,
            "tools": builtin_tools,
            "after_model_callback": self._wrapped_callback,
            "on_tool_error_callback": self._on_tool_error,
        }
        if sub_agents:
            init_kwargs["sub_agents"] = sub_agents
            logger.info(f"Initializing with {len(sub_agents)} A2A sub-agent(s)")

        super().__init__(**init_kwargs)

        # Skill registry. Default skills dir is agent/skills; AGENT_SKILLS_DIRS
        # (resolved by the caller) may add more.
        current_dir = os.path.dirname(__file__)
        if not skills_dirs:
            skills_dirs = [os.path.abspath(os.path.join(current_dir, "..", "skills"))]
        else:
            skills_dirs = [d if os.path.isabs(d) else os.path.abspath(d) for d in skills_dirs]

        self.skill_registry = SkillRegistry(skills_dirs)
        self.skill_registry.load_skills()
        self._active_skills = []

        # Remote tool metadata is lazy-loaded on first use (cannot await here).
        self.available_remote_tools = {}

        model_name_str = model if isinstance(model, str) else getattr(model, "model", str(model))
        self._mode_manager = ModeManager(model_name=model_name_str)
        self._all_available_tools = all_tools
        self._builtin_tools = builtin_tools
        self._original_callback = after_model_callback
        self._disable_mode_switching = disable_mode_switching

        self._mcp_url = mcp_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")
        self._mcp_servers = load_agent_config().mcp_servers

        # AP2 Protocol feature flag (experimental)
        self._enable_ap2 = os.getenv("ENABLE_AP2_PROTOCOL", "false").lower() == "true"
        if self._enable_ap2:
            logger.info("AP2 Protocol ENABLED via ENABLE_AP2_PROTOCOL=true")
            try:
                self._payment_handler = PaymentHandler()
            except Exception as e:
                logger.warning(f"Failed to initialize PaymentHandler: {e}")
                self._payment_handler = None
        else:
            logger.info("AP2 Protocol DISABLED (set ENABLE_AP2_PROTOCOL=true to enable)")

        logger.info(f"AdaptiveAgent initialized with MCP URL: {self._mcp_url}")

    # --- Accessors used by skill_tools closures ---

    @property
    def active_skills(self) -> List[str]:
        return self._active_skills

    @property
    def mcp_servers(self) -> Dict[str, Dict]:
        return self._mcp_servers

    @property
    def mcp_url(self) -> str:
        return self._mcp_url

    @property
    def ap2_enabled(self) -> bool:
        return self._enable_ap2

    async def ensure_remote_tools_loaded(self):
        """Lazy-load remote MCP tool metadata if not already loaded."""
        if self.available_remote_tools:
            return
        self.available_remote_tools = await remote_tools.discover_remote_tools(self._mcp_url)

    # --- Callbacks ---

    def _on_tool_error(self, tool, args: dict, tool_context, error: Exception) -> Optional[dict]:
        """
        Gracefully turn tool errors into observations for the LLM.

        AP2 Protocol: a PaymentRequiredError becomes a structured payment
        observation. The LLM decides whether to pay - we never auto-pay.
        """
        tool_name = getattr(tool, "name", str(tool)) if tool else "unknown"

        if self._enable_ap2 and isinstance(error, PaymentRequiredError) and self._payment_handler:
            logger.info(f"AP2: Payment Required for {tool_name}: {error.price} {error.currency}")
            return self._payment_handler.format_payment_error(tool_name, error)

        error_msg = str(error)
        logger.warning(f"Tool error caught: {tool_name} - {error_msg}")
        return {"error": f"Tool '{tool_name}' failed: {error_msg}"}

    async def _wrapped_callback(
        self, llm_response: LlmResponse, callback_context: CallbackContext
    ) -> Optional[LlmResponse]:
        """Run the user callback (e.g. Enforcer), then apply mode-switching logic."""
        try:
            # 1. Original callback first (e.g. Enforcer validation)
            if self._original_callback:
                if inspect.iscoroutinefunction(self._original_callback):
                    result = await self._original_callback(
                        llm_response=llm_response, callback_context=callback_context
                    )
                else:
                    result = self._original_callback(
                        llm_response=llm_response, callback_context=callback_context
                    )
                if result is not None:
                    logger.info("Enforcer blocked response")
                    return result

            # 2. Record any switch_mode tool call
            self._check_for_switch_request(llm_response)

            # 3. Switch modes if requested or the context is filling up
            context_token_count = self._estimate_context_tokens(callback_context)
            if not self._disable_mode_switching and self._mode_manager.should_switch(context_token_count):
                await self._perform_mode_switch(callback_context)

            return None
        except Exception as e:
            logger.error(f"CRITICAL ERROR in _wrapped_callback: {e}", exc_info=True)
            return None

    def _check_for_switch_request(self, llm_response: LlmResponse):
        """Check if the LLM called the switch_mode tool."""
        if llm_response.content and llm_response.content.parts:
            for part in llm_response.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    if part.function_call.name == "switch_mode":
                        args = part.function_call.args or {}
                        self._mode_manager.request_switch(
                            reason=args.get("reason", ""),
                            new_focus=args.get("new_focus", ""),
                        )

    def _estimate_context_tokens(self, callback_context: CallbackContext) -> int:
        """Rough token estimate of the session history (~4 chars per token)."""
        try:
            contents = self._session_contents(callback_context)
            total_chars = 0
            for content in contents:
                for part in getattr(content, "parts", []) or []:
                    text = getattr(part, "text", None)
                    if text:
                        total_chars += len(text)
            return total_chars // 4
        except Exception as e:
            logger.warning(f"Could not estimate token count: {e}")
        return 0

    def _extract_history_summary(self, context: CallbackContext) -> str:
        """Extract a short summary of the recent conversation history."""
        try:
            contents = self._session_contents(context)
            messages = []
            for content in contents[-5:]:
                for part in getattr(content, "parts", []) or []:
                    text = getattr(part, "text", None)
                    if text:
                        messages.append(text[:100])
            if messages:
                return " | ".join(messages)
        except Exception as e:
            logger.warning(f"Could not extract history: {e}")
        return "Conversation in progress."

    @staticmethod
    def _session_contents(context: CallbackContext) -> list:
        session = getattr(context, "session", None)
        if session is None:
            return []
        if hasattr(session, "contents"):
            return session.contents or []
        if hasattr(session, "history"):
            return session.history or []
        return []

    async def _perform_mode_switch(self, context: CallbackContext):
        """
        Executes the mode switch:
        1. Generates a new config (instruction + tool/skill selection) via the Meta-Agent.
        2. Rebuilds the toolset: built-ins + a filtered McpToolset.
        3. Clears the session history (the new instruction carries the summary).
        """
        try:
            logger.info("Initiating Mode Switch...")

            history_summary = self._extract_history_summary(context)
            requested_focus = getattr(self._mode_manager, "_requested_focus", None)

            # Expand MCP toolsets into individual tools so the Meta-Agent can see them
            expanded_available_tools = []
            original_mcp_toolset = None
            for tool in self._all_available_tools:
                if "Toolset" in type(tool).__name__:
                    original_mcp_toolset = tool
                    if hasattr(tool, "tool_filter"):
                        tool.tool_filter = None  # clear filter to see all tools
                    try:
                        mcp_tools = await tool.get_tools()
                        expanded_available_tools.extend(mcp_tools)
                        logger.info(f"Fetched {len(mcp_tools)} tools from MCP server.")
                    except Exception as e:
                        logger.error(f"Failed to fetch tools from McpToolset: {e}")
                        expanded_available_tools.append(tool)
                else:
                    expanded_available_tools.append(tool)

            # Available skills: curated + zero-config remote tools
            available_skills = []
            if self.skill_registry:
                try:
                    available_skills = self.skill_registry.list_skills()
                except Exception as e:
                    logger.error(f"Failed to list skills from registry: {e}")
            for tool_name, desc in self.available_remote_tools.items():
                available_skills.append({"name": tool_name, "description": f"[Remote Tool] {desc}"})

            new_instruction, selected_tool_names, selected_skills = self._mode_manager.generate_mode_config(
                history_summary,
                expanded_available_tools,
                available_skills,
                requested_focus,
            )

            # Append instructions of the selected skills
            for skill_name in selected_skills or []:
                skill = self.skill_registry.get_skill(skill_name) if self.skill_registry else None
                if skill and "instructions" in skill:
                    new_instruction += f"\n\n# Skill: {skill_name}\n{skill['instructions']}"
                elif skill_name in self.available_remote_tools:
                    new_instruction += (
                        f"\n\n# Tool Enabled: {skill_name}\n"
                        f"You have enabled the raw tool '{skill_name}'. Use it according to its schema."
                    )
                else:
                    logger.warning(f"Skill '{skill_name}' selected but not found.")

            # Build the new tool list: built-ins always survive
            new_tools = list(self._builtin_tools)
            if selected_tool_names:
                if original_mcp_toolset is not None:
                    if hasattr(original_mcp_toolset, "tool_filter"):
                        original_mcp_toolset.tool_filter = selected_tool_names
                        logger.info(f"Updated McpToolset filter to: {selected_tool_names}")
                    new_tools.append(original_mcp_toolset)
                elif self._mcp_url:
                    try:
                        new_tools.append(
                            McpToolset(
                                connection_params=StreamableHTTPConnectionParams(url=self._mcp_url),
                                tool_filter=selected_tool_names,
                                require_confirmation=False,
                            )
                        )
                        logger.info(f"Created McpToolset with tools: {selected_tool_names}")
                    except Exception as e:
                        logger.error(f"Failed to create McpToolset: {e}")
            elif original_mcp_toolset is not None:
                # Nothing selected: keep the original toolset as a fallback
                new_tools.append(original_mcp_toolset)

            self.instruction = new_instruction
            self.tools = new_tools
            logger.info(f"Updated agent tools: {[t.name for t in self.tools if hasattr(t, 'name')]}")

            # Clear the session history: the model should rely only on the new
            # instruction (which contains the summary) and tools.
            session = getattr(context, "session", None)
            if session is not None and hasattr(session, "contents"):
                if isinstance(session.contents, list):
                    session.contents.clear()
                    logger.info("Session history cleared.")
                else:
                    logger.warning("Could not clear session history: contents is not a list.")

        except Exception as e:
            # Never crash the agent on a failed switch
            logger.error(f"CRITICAL ERROR in _perform_mode_switch: {e}", exc_info=True)

        logger.info("Mode Switch Complete.")
