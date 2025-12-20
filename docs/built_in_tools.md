# Built-in Tools Reference

This document describes the built-in tools available to the DAK Agent. These tools are implemented within the Agent itself (Client-Side) or provided by the base `LlmAgent` class, and are essential for the agent's autonomy, skill management, and control flow.

## 1. Skill Management Tools

These tools allow the agent to dynamically discover and load new capabilities (Skills) or individual tools from the MCP server.

### `list_skills`
*   **Description**: Lists all available Agent Skills (curated YAML definitions) and individual Remote Tools (Zero-Config) available on the MCP server.
*   **Usage**: The agent uses this when it needs a capability it doesn't currently have.
*   **Returns**: A formatted list of skill names and descriptions.
*   **Implementation**: `agent/dak_agent/adaptive_agent.py` (Client-Side)

### `enable_skill`
*   **Description**: Enables a specific skill or tool.
    *   **Curated Skill**: Loads the skill's instructions into the System Prompt and activates its associated tools.
    *   **Remote Tool**: Loads the tool's schema and activates it for use.
*   **Arguments**:
    *   `skill_name` (str): The name of the skill or tool to enable.
*   **Implementation**: `agent/dak_agent/adaptive_agent.py` (Client-Side)

---

## 2. Mode Switching Tools

These tools manage the agent's context and focus.

### `switch_mode`
*   **Description**: Requests a switch in the agent's "Mode" (Context). This triggers the Dynamic Mode Switching logic, which may update the System Instruction and active toolset based on the new focus.
*   **Arguments**:
    *   `reason` (str): The reason for switching modes.
    *   `new_focus` (str): The new topic or task to focus on.
*   **Implementation**: `agent/dak_agent/adaptive_agent.py` (Overrides base implementation)

---

## 3. Enforcer Mode Tools

These tools are active when the agent is in **Enforcer Mode** (Strict Mode), enforcing a "Think, Plan, Act" loop.

### `planner`
*   **Description**: Creates a plan of execution. The agent *must* call this before using any other tools in Enforcer Mode.
*   **Arguments**:
    *   `steps` (List[str]): A list of steps to execute.
    *   `allowed_tools` (List[str]): (Optional) Tools allowed for this plan.

### `attempt_answer`
*   **Description**: Provides the final answer to the user. This signals the end of the task or turn.
*   **Arguments**:
    *   `answer` (str): The final response text.

### `ask_question`
*   **Description**: Asks the user a clarifying question. This pauses execution to wait for user input.
*   **Arguments**:
    *   `question` (str): The question to ask.

---

## 4. Standard MCP Tools (Server-Side)

These tools are provided by the MCP Server (`mcp-server/`) and are what the agent typically uses to perform actual work. They are loaded dynamically or via Skills.

*   `read_file`: Read file contents.
*   `write_file`: Write to a file.
*   `list_files`: List directory contents.
*   `search_files`: Search for files.
*   `run_command`: Execute a shell command (if enabled).
