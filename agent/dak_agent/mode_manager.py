import logging
import os
from typing import List, Tuple, Any, Optional

logger = logging.getLogger(__name__)


class ModeManager:
    """
    Manages the "Mode" of the agent.
    A Mode consists of:
    1. A specific System Instruction (Prompt).
    2. A specific set of Allowed Tools.
    
    Triggers:
    - Initial request (first turn of session)
    - Token count exceeds threshold (50% of max)
    - LLM calls `switch_mode` tool
    """
    
    # Model context window sizes (approximate)
    MODEL_MAX_TOKENS = {
        "gemini-2.5-flash": 1000000,
        "gemini-2.5-pro": 1000000,
        "gemini-3-pro-preview": 1000000,
        "gemini-2.0-flash-exp": 1000000,
        "default": 128000,
    }
    
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self.max_context_tokens = self.MODEL_MAX_TOKENS.get(
            model_name, 
            self.MODEL_MAX_TOKENS["default"]
        )
        self.token_threshold = 0.5  # 50% threshold
        self._is_first_turn = True
        self._switch_requested = False
    
    def should_switch(self, context_token_count: int = 0) -> bool:
        """
        Decides if a mode switch is necessary.
        
        Triggers:
        1. First turn of session (initial mode setup)
        2. Token count >= 50% of max context
        3. LLM explicitly requested switch via switch_mode tool
        """
        # Trigger 1: Initial request
        if self._is_first_turn:
            logger.info("Mode Switch Triggered: Initial request (first turn)")
            self._is_first_turn = False
            return True
        
        # Trigger 2: Token threshold exceeded
        if context_token_count > 0:
            usage_ratio = context_token_count / self.max_context_tokens
            if usage_ratio >= self.token_threshold:
                logger.info(f"Mode Switch Triggered: Token usage ({usage_ratio:.1%}) >= threshold ({self.token_threshold:.0%})")
                return True
        
        # Trigger 3: LLM requested switch
        if self._switch_requested:
            logger.info("Mode Switch Triggered: LLM requested via switch_mode tool")
            self._switch_requested = False
            return True
        
        return False
    
    def request_switch(self, reason: str, new_focus: str):
        """Called when LLM uses the switch_mode tool."""
        logger.info(f"Switch requested by LLM. Reason: {reason}, New focus: {new_focus}")
        self._switch_requested = True
        self._requested_focus = new_focus
    
    def reset_session(self):
        """Reset for a new session."""
        self._is_first_turn = True
        self._switch_requested = False

    def generate_mode_config(
        self, 
        history_summary: str, 
        available_tools: List[Any],
        model_client: Any,
        requested_focus: Optional[str] = None
    ) -> Tuple[str, List[Any]]:
        """
        Generates a new mode configuration (Instruction, Tools) using a Meta-LLM call.
        
        Args:
            history_summary: A summary of the conversation so far.
            available_tools: The full list of tools available to the agent.
            model_client: The LLM client to use for the Meta-Agent call.
            requested_focus: If LLM requested a specific focus via switch_mode.
            
        Returns:
            Tuple[str, List[Any]]: (New System Instruction, List of Selected Tools)
        """
        
        # Prepare Tool Descriptions for the Meta-Agent
        tool_descriptions = []
        tool_map = {}
        for tool in available_tools:
            name = getattr(tool, 'name', str(tool))
            description = getattr(tool, 'description', "No description")
            tool_descriptions.append(f"- {name}: {description}")
            tool_map[name] = tool

        tools_block = "\n".join(tool_descriptions)

        # Construct the Meta-Prompt
        focus_hint = ""
        if requested_focus:
            focus_hint = f"\n# LLM Requested Focus\n{requested_focus}\n"
        
        meta_prompt = f"""
You are a "Meta-Agent" responsible for optimizing another AI agent's performance.
The current agent has been running for a while and its context is getting full.
You need to create a NEW, focused configuration for this agent to continue the task efficiently.

# Current Context / Goal
{history_summary}
{focus_hint}
# Available Tools
{tools_block}

# Your Task
1. Analyze the current situation. What is the immediate next step?
2. Write a CONCISE System Instruction for the agent to focus ONLY on this next step.
   - The instruction should be specific, not generic.
   - It should summarize the relevant past context so the agent knows what happened.
3. Select ONLY the strictly necessary tools from the list above.
   - Fewer tools = better focus.

# Output Format
You must output a JSON object with this structure:
{{
  "instruction": "The new system prompt...",
  "selected_tools": ["tool_name_1", "tool_name_2"]
}}
"""

        # Log instead of print
        logger.debug("--- META-AGENT PROMPT ---")
        logger.debug(meta_prompt)
        logger.debug("-------------------------")

        try:
            # Call the Meta-Agent (LLM) using the provided client
            response = model_client.models.generate_content(
                model=self.model_name,
                contents=meta_prompt,
                config={
                    'response_mime_type': 'application/json'
                }
            )
            
            if not response.text:
                logger.warning("Meta-Agent returned empty response. Keeping current configuration.")
                return "Continue with current task.", []

            # Parse JSON response
            import json
            config_data = json.loads(response.text)
            
            new_instruction = config_data.get("instruction", "Continue with current task.")
            selected_tool_names = config_data.get("selected_tools", [])
            
            logger.info(f"Meta-Agent selected tools: {selected_tool_names}")
            
            # Return instruction and list of selected tool names
            # AdaptiveAgent will use these names to create a filtered McpToolset
            return new_instruction, selected_tool_names

        except Exception as e:
            logger.error(f"Meta-Agent failed: {e}. Reverting to default configuration.")
            # Fallback: Return generic instruction and empty list (will use all tools)
            return "Continue with current task.", []
