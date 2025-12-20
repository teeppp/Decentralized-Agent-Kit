import logging
import os
from typing import List, Any, Optional, Callable, Dict
from google.adk.agents import LlmAgent
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.adk.tools.base_toolset import BaseToolset
from pydantic import PrivateAttr, ConfigDict, Field
from .mode_manager import ModeManager
from google import genai
import inspect

logger = logging.getLogger(__name__)


from google.adk.tools import FunctionTool

class AdaptiveAgent(LlmAgent):
    """
    A wrapper around LlmAgent that implements Dynamic Mode Switching.
    
    Mode switching is triggered by:
    1. Initial request (first turn) - always triggers
    2. Token count exceeds 50% of context window
    3. LLM calls the `switch_mode` tool
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
from .skill_registry import SkillRegistry
import subprocess

class AdaptiveAgent(LlmAgent):
    """
    A wrapper around LlmAgent that implements Dynamic Mode Switching and Agent Skills.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # Override tools field to allow ProxyMcpToolset
    tools: List[Any] = []

    # Private attributes for internal state
    _mode_manager: ModeManager = PrivateAttr()
    _all_available_tools: List[Any] = PrivateAttr()
    _builtin_tools: List[Any] = PrivateAttr()  # FunctionTools that never get filtered
    _original_callback: Optional[Any] = PrivateAttr(default=None)
    _disable_mode_switching: bool = PrivateAttr(default=False)
    _mcp_url: str = PrivateAttr(default="")
    _meta_agent_client: Optional[genai.Client] = PrivateAttr(default=None)
    skill_registry: Optional[SkillRegistry] = Field(default=None, exclude=True)
    available_remote_tools: Dict[str, str] = Field(default_factory=dict, exclude=True)
    _active_skills: List[str] = PrivateAttr(default=[])
    
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
        # Define Client-Side Tools
        
        async def list_skills() -> str:
            """
            List all available Agent Skills and Remote Tools.
            Returns a list of skills and tools with their names and descriptions.
            """
            # Ensure remote tools are loaded
            await self._ensure_remote_tools_loaded()
            
            output = []
            
            # 1. Local Skills
            if self.skill_registry:
                skills = self.skill_registry.list_skills()
                if skills:
                    output.append("## Curated Skills (Recommended)")
                    output.extend([f"- {s['name']}: {s['description']}" for s in skills])
            
            # 2. Remote Tools (Zero-Config)
            if self.available_remote_tools:
                output.append("\n## Individual Remote Tools")
                output.extend([f"- {name}: {desc}" for name, desc in self.available_remote_tools.items()])
            
            if not output:
                return "No skills or tools available."
            
            return "\n".join(output)

        async def enable_skill(skill_name: str) -> str:
            """
            Enable a specific skill OR an individual remote tool.
            This loads the instructions and makes the tools available.
            """
            # Ensure remote tools are loaded
            await self._ensure_remote_tools_loaded()
            
            # Check if it's a curated skill
            skill = self.skill_registry.get_skill(skill_name) if self.skill_registry else None
            
            tools_to_add = []
            instructions_to_add = ""
            
            if skill:
                # It's a curated skill
                if skill_name in self._active_skills:
                    return f"Skill '{skill_name}' is already active."
                self._active_skills.append(skill_name)
                
                if 'instructions' in skill:
                    instructions_to_add = f"\n\n# Skill: {skill_name}\n{skill['instructions']}"
                
                tools_to_add = skill.get('tools', [])
                
            elif skill_name in self.available_remote_tools:
                # It's a raw remote tool (Zero-Config)
                if skill_name in self._active_skills:
                    return f"Tool '{skill_name}' is already active."
                self._active_skills.append(skill_name)
                
                # No specific instructions for raw tools, but we can add a generic one
                instructions_to_add = f"\n\n# Tool Enabled: {skill_name}\nYou have enabled the raw tool '{skill_name}'. Use it according to its schema."
                
                tools_to_add = [skill_name]
            else:
                return f"Error: Skill or Tool '{skill_name}' not found."

            # Apply Instructions
            if instructions_to_add:
                self.instruction += instructions_to_add
            
            # Apply Tools
            required_tools = set(tools_to_add)
            
            current_tool_names = set()
            for t in self.tools:
                name = getattr(t, 'name', None)
                if name:
                    current_tool_names.add(name)
            
            tools_to_add_from_mcp = []
            for tool_name in required_tools:
                if tool_name not in current_tool_names:
                    tools_to_add_from_mcp.append(tool_name)
            
            if tools_to_add_from_mcp:
                if self._mcp_url:
                    try:
                        filtered_toolset = McpToolset(
                            connection_params=StreamableHTTPConnectionParams(url=self._mcp_url),
                            tool_filter=tools_to_add_from_mcp,
                            require_confirmation=False
                        )
                        self.tools.append(filtered_toolset)
                        logger.info(f"Added filtered McpToolset for tools: {tools_to_add_from_mcp}")
                    except Exception as e:
                        logger.error(f"Failed to create McpToolset for {skill_name}: {e}")
                        return f"Error enabling {skill_name}: Failed to connect to tools. {e}"
            
            return f"'{skill_name}' enabled."



        # Override switch_mode tool to have access to tools list
        # We do this BEFORE calling super().__init__ to ensure LlmAgent registers the correct tool.
        
        # Define the custom tool function capturing 'tools' from argument
        def switch_mode(reason: str = "", new_focus: str = "") -> str:
            """
            Request a mode switch.
            """
            return f"Mode switch requested: {reason}. New focus: {new_focus}"

        # Create the overridden switch_mode tool
        modified_tools = []
        for tool in tools:
            if getattr(tool, 'name', '') == 'switch_mode':
                modified_tools.append(FunctionTool(switch_mode, require_confirmation=False))
            else:
                modified_tools.append(tool)
        
        # Add Client-Side Tools
        modified_tools.append(FunctionTool(list_skills, require_confirmation=False))
        modified_tools.append(FunctionTool(enable_skill, require_confirmation=False))
        
        # Define a callback to gracefully handle tool errors
        def on_tool_error_handler(tool, args: dict, tool_context, error: Exception) -> Optional[dict]:
            tool_name = getattr(tool, 'name', str(tool)) if tool else "unknown"
            error_msg = str(error)
            logger.warning(f"Tool error caught: {tool_name} - {error_msg}")
            return {"error": f"Tool '{tool_name}' failed: {error_msg}"}
        
        # Prepare local variables for initial toolset calculation
        builtin_tools = []
        original_mcp_toolset = None
        
        for tool in modified_tools:
            tool_class = type(tool).__name__
            if 'McpToolset' not in tool_class and 'Toolset' not in tool_class:
                builtin_tools.append(tool)
            elif 'McpToolset' in tool_class or 'Toolset' in tool_class:
                original_mcp_toolset = tool

        # Determine initial tools
        # Start with ONLY Built-in tools (Skills + Switch Mode). Hide MCP tools.
        initial_tools = builtin_tools
        logger.info("Initializing with minimal toolset (Client-Side Skills + Built-in)")

        # Initialize the parent LlmAgent with initial tools
        super().__init__(
            model=model,
            name=name,
            instruction=instruction,
            tools=initial_tools,
            after_model_callback=self._wrapped_callback,
            on_tool_error_callback=on_tool_error_handler
        )
        
        # Initialize SkillRegistry AFTER super().__init__
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        skills_dir = os.path.join(project_root, "agent", "skills")
        self.skill_registry = SkillRegistry(skills_dir)
        self.skill_registry.load_skills()
        self._active_skills = []
        
        # Zero-Config: Fetch available remote tools (metadata only)
        self.available_remote_tools = {} # name -> description
        # We cannot fetch them synchronously here. They will be lazy-loaded.
        
        # Initialize private attributes
        model_name_str = getattr(model, 'model', str(model)) if not isinstance(model, str) else model
        self._mode_manager = ModeManager(model_name=model_name_str)
        self._all_available_tools = modified_tools
        self._builtin_tools = builtin_tools
        self._original_callback = after_model_callback
        self._disable_mode_switching = disable_mode_switching
        
        # Store MCP URL
        self._mcp_url = mcp_url or os.getenv("MCP_SERVER_URL", "http://mcp-server:8000/mcp")
        logger.info(f"AdaptiveAgent initialized with MCP URL: {self._mcp_url}")

    async def _ensure_remote_tools_loaded(self):
        """Lazy load remote tools if not already loaded."""
        if self.available_remote_tools:
            return

        target_mcp_url = self._mcp_url
        if not target_mcp_url:
            return

        try:
            logger.info(f"Connecting to MCP server at: {target_mcp_url}")
            temp_toolset = McpToolset(
                connection_params=StreamableHTTPConnectionParams(url=target_mcp_url),
                require_confirmation=False
            )
            # Fetch tools asynchronously
            tools = await temp_toolset.get_tools()
            
            for tool in tools:
                name = getattr(tool, 'name', None)
                desc = getattr(tool, 'description', "No description")
                if name:
                    self.available_remote_tools[name] = desc
            logger.info(f"Discovered {len(self.available_remote_tools)} remote tools.")
        except Exception as e:
            logger.warning(f"Failed to discover remote tools: {e}")
        
        # Initialize LLM client for Meta-Agent
        try:
            self._meta_agent_client = genai.Client()
        except Exception as e:
            logger.warning(f"Failed to initialize GenAI client for Meta-Agent: {e}")
            self._meta_agent_client = None




    async def _wrapped_callback(self, llm_response: LlmResponse, callback_context: CallbackContext) -> Optional[LlmResponse]:
        """
        Wraps the user-provided callback to add mode switching logic.
        """
        try:
            logger.info("Entering _wrapped_callback")
            # 1. Call the original callback first (e.g., Enforcer validation)
            enforcer_result = None
            if self._original_callback:
                try:
                    # Check if original callback is async
                    if inspect.iscoroutinefunction(self._original_callback):
                        enforcer_result = await self._original_callback(llm_response=llm_response, callback_context=callback_context)
                    else:
                        enforcer_result = self._original_callback(llm_response=llm_response, callback_context=callback_context)
                except TypeError:
                    # Fallback for positional args
                    if inspect.iscoroutinefunction(self._original_callback):
                        enforcer_result = await self._original_callback(llm_response, callback_context)
                    else:
                        enforcer_result = self._original_callback(llm_response, callback_context)
                
                # If Enforcer blocked the response, return immediately without mode switching
                if enforcer_result is not None:
                    logger.info("Enforcer blocked response")
                    return enforcer_result
            
            # 2. Check for switch_mode tool call in LLM response
            logger.info("Checking for switch request")
            self._check_for_switch_request(llm_response)
            
            # 3. Estimate current context token count
            logger.info("Estimating tokens")
            context_token_count = self._estimate_context_tokens(callback_context)
            logger.info(f"Token count: {context_token_count}")
            
            # 4. Check if mode switch should occur
            if not self._disable_mode_switching and self._mode_manager.should_switch(context_token_count):
                logger.info("Performing mode switch")
                await self._perform_mode_switch(callback_context)
            
            logger.info("Exiting _wrapped_callback")
            return None
        except Exception as e:
            logger.error(f"CRITICAL ERROR in _wrapped_callback: {e}", exc_info=True)
            return None
    
    def _check_for_switch_request(self, llm_response: LlmResponse):
        """Check if LLM called the switch_mode tool."""
        if llm_response.content and llm_response.content.parts:
            for part in llm_response.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    logger.info(f"LLM Function Call: {part.function_call.name}")
                    if part.function_call.name == "switch_mode":
                        args = part.function_call.args or {}
                        logger.info(f"Switch Mode Args: {args}")
                        
                        # Check if this is a query for tool list
                        self._mode_manager.request_switch(
                            reason=args.get("reason", ""),
                            new_focus=args.get("new_focus", "")
                        )
    
    def _estimate_context_tokens(self, callback_context: CallbackContext) -> int:
        """Estimate the number of tokens in the current context."""
        try:
            if hasattr(callback_context, 'session') and callback_context.session:
                # DEBUG: Inspect session object
                # logger.info(f"Session attributes: {dir(callback_context.session)}")
                
                # Check for 'contents' or 'history'
                contents = []
                if hasattr(callback_context.session, 'contents'):
                    contents = callback_context.session.contents or []
                elif hasattr(callback_context.session, 'history'):
                    contents = callback_context.session.history or []
                else:
                    # logger.warning(f"Session object has no 'contents' or 'history'. Attributes: {dir(callback_context.session)}")
                    pass

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

    def _extract_history_summary(self, context: CallbackContext) -> str:
        """Extract a summary of the conversation history."""
        try:
            if hasattr(context, 'session') and context.session:
                contents = []
                if hasattr(context.session, 'contents'):
                    contents = context.session.contents or []
                elif hasattr(context.session, 'history'):
                    contents = context.session.history or []
                
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

    async def _perform_mode_switch(self, context: CallbackContext):
        """
        Executes the mode switch:
        1. Generates new config via ModeManager (gets selected tool names).
        2. Creates a new McpToolset with tool_filter to reduce context.
        3. Combines with built-in tools and updates agent.
        """
        try:
            if not self._meta_agent_client:
                logger.warning("Skipping mode switch: Meta-Agent client not initialized.")
                return

            logger.info("Initiating Mode Switch...")
            
            # Get history summary from context
            history_summary = self._extract_history_summary(context)
            
            # Get requested focus if any
            requested_focus = getattr(self._mode_manager, '_requested_focus', None)
            
            # PREPARE TOOLS FOR META-AGENT
            # We need to expand McpToolset into individual tools so Meta-Agent can see them
            expanded_available_tools = []
            original_mcp_toolset = None
            
            for tool in self._all_available_tools:
                tool_class = type(tool).__name__
                if 'McpToolset' in tool_class or 'Toolset' in tool_class:
                    original_mcp_toolset = tool
                    # TEMPORARILY CLEAR FILTER to see all tools
                    if hasattr(tool, 'tool_filter'):
                        logger.info("Clearing McpToolset filter for inspection.")
                        tool.tool_filter = None

                    # Fetch actual tools from MCP server
                    try:
                        logger.info("Fetching MCP tools for Meta-Agent inspection...")
                        mcp_tools = await tool.get_tools()
                        expanded_available_tools.extend(mcp_tools)
                        logger.info(f"Fetched {len(mcp_tools)} tools from MCP server.")
                        
                    except Exception as e:
                        logger.error(f"Failed to fetch tools from McpToolset: {e}")
                        # Fallback: add the toolset itself (better than nothing)
                        expanded_available_tools.append(tool)
                else:
                    expanded_available_tools.append(tool)
            
            # Fetch Available Skills (Client-Side)
            available_skills = []
            if self.skill_registry:
                try:
                    logger.info("Fetching available skills from registry...")
                    available_skills = self.skill_registry.list_skills()
                    logger.info(f"Fetched {len(available_skills)} skills.")
                except Exception as e:
                    logger.error(f"Failed to list skills from registry: {e}")
            
            # Add Zero-Config Tools as "Skills" for Meta-Agent consideration
            if self.available_remote_tools:
                for name, desc in self.available_remote_tools.items():
                    available_skills.append({
                        "name": name,
                        "description": f"[Remote Tool] {desc}"
                    })

            # Get new instruction and selected tool names from Meta-Agent
            new_instruction, selected_tool_names, selected_skills = self._mode_manager.generate_mode_config(
                history_summary, 
                expanded_available_tools,
                available_skills,
                self._meta_agent_client,
                requested_focus
            )
            
            # Load Selected Skills Instructions
            if selected_skills:
                logger.info(f"Loading instructions for skills: {selected_skills}")
                skill_instructions = []
                for skill_name in selected_skills:
                    try:
                        # Check local registry first
                        skill = self.skill_registry.get_skill(skill_name) if self.skill_registry else None
                        if skill and 'instructions' in skill:
                            skill_instructions.append(f"\n\n# Skill: {skill_name}\n{skill['instructions']}")
                        elif skill_name in self.available_remote_tools:
                            # Zero-Config Tool
                            skill_instructions.append(f"\n\n# Tool Enabled: {skill_name}\nYou have enabled the raw tool '{skill_name}'. Use it according to its schema.")
                        else:
                            logger.warning(f"Skill '{skill_name}' selected but not found.")
                    except Exception as e:
                        logger.error(f"Failed to load skill '{skill_name}': {e}")
                
                if skill_instructions:
                    new_instruction += "".join(skill_instructions)
                    logger.info("Appended skill instructions to system prompt.")
            
            # Build new tool list
            new_tools = list(self._builtin_tools)  # Always include built-in tools (planner, switch_mode, etc.)
            
            # Create filtered toolset if tool names were selected
            if selected_tool_names:
                # REUSE EXISTING TOOLSET and update filter
                if original_mcp_toolset:
                    if hasattr(original_mcp_toolset, 'tool_filter'):
                        original_mcp_toolset.tool_filter = selected_tool_names
                        logger.info(f"Updated McpToolset filter to: {selected_tool_names}")
                    new_tools.append(original_mcp_toolset)
                
                # Fallback: Create new toolset if original not found (should not happen usually)
                elif self._mcp_url:
                    logger.info(f"Attempting to create McpToolset with URL: {self._mcp_url} and tools: {selected_tool_names}")
                    try:
                        # Use McpToolset with filter
                        filtered_toolset = McpToolset(
                            connection_params=StreamableHTTPConnectionParams(url=self._mcp_url),
                            tool_filter=selected_tool_names,
                            require_confirmation=False
                        )
                        new_tools.append(filtered_toolset)
                        logger.info(f"Created McpToolset with tools: {selected_tool_names}")
                        
                    except Exception as e:
                        logger.error(f"Failed to create McpToolset: {e}")
                else:
                    logger.warning("MCP URL not available and no original toolset, cannot create filtered toolset.")
            else:
                logger.warning("No McpToolset found in available tools.")
                # No tools selected - include original McpToolset
                if original_mcp_toolset:
                    new_tools.append(original_mcp_toolset)
                    logger.warning(f"Fallback: using original McpToolset")

            
            # Update Agent Configuration
            self.instruction = new_instruction
            self.tools = new_tools
            logger.info(f"Updated agent tools: {[t.name for t in self.tools if hasattr(t, 'name')]}")
            
            # CRITICAL: Clear the session history (User/Model messages)
            # This ensures the model relies ONLY on the new System Instruction and Tools.
            # The new instruction contains the summary of the previous context.
            if hasattr(context, 'session') and context.session:
                try:
                    # Clear the contents list to reset history
                    # Note: This depends on the specific GenAI SDK implementation.
                    # For google-genai-sdk, modifying the list in place or re-assigning might work.
                    # We'll try to clear the list.
                    if hasattr(context.session, 'contents'):
                        # Create a fresh list if possible, or clear existing
                        # context.session.contents.clear() # If it's a list
                        # Re-assigning to empty list is safer if setter exists
                        # context.session.contents = [] 
                        
                        # Let's try to find the best way to clear it based on the object type
                        # Assuming it's a list-like object or we can replace it.
                        # For now, we will try to clear the list.
                        if isinstance(context.session.contents, list):
                            context.session.contents.clear()
                            logger.info("Session history cleared.")
                        else:
                            # If it's not a direct list, we might need to reset the session object itself
                            # or use a specific method. 
                            # Since we don't have full introspection here, we'll try a best effort.
                            logger.warning("Could not clear session history: contents is not a list.")
                except Exception as e:
                    logger.warning(f"Failed to clear session history: {e}")
                    
        except Exception as e:
            logger.error(f"CRITICAL ERROR in _perform_mode_switch: {e}", exc_info=True)
            # Do not re-raise to prevent agent crash

        logger.info("Mode Switch Complete.")
    
    def _extract_history_summary(self, context: CallbackContext) -> str:
        """Extract a summary of the conversation history."""
        try:
            if hasattr(context, 'session') and context.session:
                contents = []
                if hasattr(context.session, 'contents'):
                    contents = context.session.contents or []
                elif hasattr(context.session, 'history'):
                    contents = context.session.history or []
                
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
