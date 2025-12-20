import os
import yaml
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class SkillRegistry:
    """
    Manages the loading, validation, and retrieval of Agent Skills.
    """
    
    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.loaded = False

    def load_skills(self):
        """Load all skills from the skills directory."""
        if not os.path.exists(self.skills_dir):
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return

        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                skill_name = os.path.splitext(filename)[0]
                filepath = os.path.join(self.skills_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        skill_data = yaml.safe_load(f)
                        if self._validate_skill_format(skill_name, skill_data):
                            self.skills[skill_name] = skill_data
                            logger.info(f"Loaded skill: {skill_name}")
                except Exception as e:
                    logger.error(f"Failed to load skill {skill_name}: {e}")
        
        self.loaded = True

    def _validate_skill_format(self, name: str, data: Dict) -> bool:
        """Basic format validation for a skill."""
        required_fields = ['name', 'description', 'tools', 'instructions']
        for field in required_fields:
            if field not in data:
                logger.error(f"Skill '{name}' missing required field: {field}")
                return False
        return True

    def validate_skills_against_tools(self, available_tools: List[Any]) -> None:
        """
        Reconcile skills with available MCP tools.
        Removes missing tools from skills. Disables skills if all tools are missing.
        """
        if not self.loaded:
            self.load_skills()
            
        # Create a set of available tool names
        available_tool_names = set()
        for tool in available_tools:
            name = getattr(tool, 'name', str(tool))
            available_tool_names.add(name)
            
        # Also include built-in tools that might be available locally
        # For now, we assume 'run_script' is available if implemented in Agent
        available_tool_names.add('run_script') 

        skills_to_remove = []

        for skill_name, skill_data in self.skills.items():
            required_tools = skill_data.get('tools', [])
            valid_tools = []
            missing_tools = []

            for tool_name in required_tools:
                if tool_name in available_tool_names:
                    valid_tools.append(tool_name)
                else:
                    missing_tools.append(tool_name)
            
            if missing_tools:
                logger.warning(f"Skill '{skill_name}' missing tools: {missing_tools}")
                # Update instructions to reflect missing tools
                if 'instructions' in skill_data:
                    skill_data['instructions'] += f"\n\n(Note: The following tools are currently unavailable: {', '.join(missing_tools)})"

            if not valid_tools:
                logger.warning(f"Skill '{skill_name}' has NO valid tools. Disabling.")
                skills_to_remove.append(skill_name)
            else:
                skill_data['tools'] = valid_tools

        for name in skills_to_remove:
            del self.skills[name]

    def get_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        return self.skills.get(skill_name)

    def list_skills(self) -> List[Dict[str, str]]:
        """Return a list of available skills (metadata only)."""
        return [
            {"name": name, "description": data['description']}
            for name, data in self.skills.items()
        ]
