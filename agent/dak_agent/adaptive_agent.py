import logging
import os
from typing import List, Any, Optional, Callable
from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from pydantic import PrivateAttr, ConfigDict
from .mode_manager import ModeManager
from google import genai

logger = logging.getLogger(__name__)


class AdaptiveAgent(LlmAgent):
    """
    A wrapper around LlmAgent that implements Dynamic Mode Switching.
    
    Mode switching is triggered by:
    1. Initial request (first turn) - always triggers
    2. Token count exceeds 50% of context window
    3. LLM calls the `switch_mode` tool
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # Private attributes for internal state
    _mode_manager: ModeManager = PrivateAttr()
    _all_available_tools: List[Any] = PrivateAttr()
    _builtin_tools: List[Any] = PrivateAttr()  # FunctionTools that never get filtered
    _original_callback: Optional[Callable] = PrivateAttr(default=None)
    _disable_mode_switching: bool = PrivateAttr(default=False)
    _meta_agent_client: Optional[Any] = PrivateAttr(default=None)
    _mcp_url: Optional[str] = PrivateAttr(default=None)
    
    def __init__(
        self, 
        model: str,
        name: str,
        instruction: str,
        tools: List[Any],
        after_model_callback: Optional[Any] = None,
        disable_mode_switching: bool = False,
        mcp_url: Optional[str] = None
    ):
        # Initialize the parent LlmAgent first
        super().__init__(
            model=model,
            name=name,
            instruction=instruction,
            tools=tools,
            after_model_callback=self._wrapped_callback
        )
        
        # Separate built-in tools from McpToolset
        builtin_tools = []
        for tool in tools:
            tool_class = type(tool).__name__
            if 'McpToolset' not in tool_class and 'Toolset' not in tool_class:
                builtin_tools.append(tool)
        
        # Initialize private attributes
        self._mode_manager = ModeManager(model_name=model)
        self._all_available_tools = tools
        self._builtin_tools = builtin_tools
        self._original_callback = after_model_callback
        self._disable_mode_switching = disable_mode_switching
        self._mcp_url = mcp_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")
        
        # Initialize LLM client for Meta-Agent
        try:
            self._meta_agent_client = genai.Client()
        except Exception as e:
            logger.warning(f"Failed to initialize GenAI client for Meta-Agent: {e}")
            self._meta_agent_client = None

    def _wrapped_callback(self, llm_response: LlmResponse, callback_context: CallbackContext) -> Optional[LlmResponse]:
        """
        Wraps the user-provided callback to add mode switching logic.
        """
        # 1. Call the original callback first (e.g., Enforcer validation)
        enforcer_result = None
        if self._original_callback:
            try:
                enforcer_result = self._original_callback(llm_response=llm_response, callback_context=callback_context)
            except TypeError:
                enforcer_result = self._original_callback(llm_response, callback_context)
            
            # If Enforcer blocked the response, return immediately without mode switching
            if enforcer_result is not None:
                return enforcer_result
        
        # 2. Check for switch_mode tool call in LLM response
        self._check_for_switch_request(llm_response)
        
        # 3. Estimate current context token count
        context_token_count = self._estimate_context_tokens(callback_context)
        
        # 4. Check if mode switch should occur
        if not self._disable_mode_switching and self._mode_manager.should_switch(context_token_count):
            self._perform_mode_switch(callback_context)
        
        return None
    
    def _check_for_switch_request(self, llm_response: LlmResponse):
        """Check if LLM called the switch_mode tool."""
        if llm_response.content and llm_response.content.parts:
            for part in llm_response.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    if part.function_call.name == "switch_mode":
                        args = part.function_call.args or {}
                        self._mode_manager.request_switch(
                            reason=args.get("reason", ""),
                            new_focus=args.get("new_focus", "")
                        )
    
    def _estimate_context_tokens(self, callback_context: CallbackContext) -> int:
        """
        Estimate the current context token count.
        
        This is a rough estimation based on session contents.
        Actual implementation should use a tokenizer or API response metadata.
        """
        try:
            if hasattr(callback_context, 'session') and callback_context.session:
                contents = callback_context.session.contents or []
                # Rough estimation: ~4 chars per token
                total_chars = 0
                for content in contents:
                    if hasattr(content, 'parts'):
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                total_chars += len(part.text)
                return total_chars // 4
        except Exception as e:
            logger.warning(f"Could not estimate token count: {e}")
        return 0

    def _perform_mode_switch(self, context: CallbackContext):
        """
        Executes the mode switch:
        1. Generates new config via ModeManager (gets selected tool names).
        2. Creates a new McpToolset with tool_filter to reduce context.
        3. Combines with built-in tools and updates agent.
        """
        if not self._meta_agent_client:
            logger.warning("Skipping mode switch: Meta-Agent client not initialized.")
            return

        logger.info("Initiating Mode Switch...")
        
        # Get history summary from context
        history_summary = self._extract_history_summary(context)
        
        # Get requested focus if any
        requested_focus = getattr(self._mode_manager, '_requested_focus', None)
        
        # Get new instruction and selected tool names from Meta-Agent
        new_instruction, selected_tool_names = self._mode_manager.generate_mode_config(
            history_summary, 
            self._all_available_tools,
            self._meta_agent_client,
            requested_focus
        )
        
        # Build new tool list
        new_tools = list(self._builtin_tools)  # Always include built-in tools (planner, switch_mode, etc.)
        
        # Create filtered McpToolset if tool names were selected
        if selected_tool_names:
            try:
                # Create a new McpToolset with tool_filter
                class FilteredMcpToolset(McpToolset):
                    model_config = ConfigDict(arbitrary_types_allowed=True)
                
                filtered_mcp = FilteredMcpToolset(
                    connection_params=StreamableHTTPConnectionParams(url=self._mcp_url),
                    tool_filter=selected_tool_names,
                    require_confirmation=True
                )
                new_tools.append(filtered_mcp)
                logger.info(f"Created filtered McpToolset with tools: {selected_tool_names}")
            except Exception as e:
                logger.error(f"Failed to create filtered McpToolset: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: use original McpToolset
                for tool in self._all_available_tools:
                    tool_class = type(tool).__name__
                    if 'McpToolset' in tool_class or 'Toolset' in tool_class:
                        new_tools.append(tool)
                        logger.warning(f"Fallback: using original {tool_class}")
        else:
            # No tools selected - include original McpToolset
            for tool in self._all_available_tools:
                tool_class = type(tool).__name__
                if 'McpToolset' in tool_class or 'Toolset' in tool_class:
                    new_tools.append(tool)
        
        # Update Agent Configuration
        self.instruction = new_instruction
        self.tools = new_tools
        
        logger.info("Mode Switch Complete.")
    
    def _extract_history_summary(self, context: CallbackContext) -> str:
        """Extract a summary of the conversation history."""
        try:
            if hasattr(context, 'session') and context.session:
                contents = context.session.contents or []
                # Get the last few messages as summary
                messages = []
                for content in contents[-5:]:  # Last 5 messages
                    if hasattr(content, 'parts'):
                        for part in content.parts:
                            if hasattr(part, 'text') and part.text:
                                messages.append(part.text[:100])  # Truncate
                return " | ".join(messages)
        except Exception as e:
            logger.warning(f"Could not extract history: {e}")
        return "Conversation in progress."
