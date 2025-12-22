# Agent Evaluation System

This directory contains a scenario-based evaluation system for the Decentralized Agent Kit. It is designed to test the agent's capabilities, logic, tool usage, and safety features in a realistic environment.

## Features

- **Scenario-Based Testing**: Define complex test cases in YAML.
- **Workflow Awareness**: Supports multi-step workflows (e.g., Plan -> Execute).
- **Tool Confirmation Support**: Automatically handles `require_confirmation=True` by approving tool calls via the API.
- **Detailed Reporting**: Generates a Markdown report (`evaluation_report.md`) with summary statistics and detailed logs.
- **Flexible Assertions**: Supports text matching, tool call verification, and semantic checks using an LLM.

## Prerequisites

- Python 3.12+
- `uv` (Project dependency manager)
- Docker (to run the agent)

## Setup

1.  **Install Dependencies**:
    Navigate to the `evaluation` directory and install dependencies:
    ```bash
    cd evaluation
    uv sync
    ```

2.  **Start the Agent**:
    Ensure the agent services are running:
    ```bash
    cd ../cli
    docker compose up -d
    ```

## Usage

Run the evaluation script using `uv`:

```bash
uv run python run_eval.py [OPTIONS]
```

### Options

- `--file <path>`: Run a specific scenario file (default: `scenarios.yaml`).
- `--tags <tag>`: Run only scenarios with the specified tag (e.g., `basic`, `workflow`, `safety`).
- `--help`: Show help message.

### Examples

**Run all scenarios in default file:**
```bash
uv run python run_eval.py
```

**Run only workflow tests:**
```bash
uv run python run_eval.py --tags workflow
```

**Run a specific test file:**
```bash
uv run python run_eval.py --file my_test.yaml
```

## Configuration

The system uses environment variables for configuration. You can set these in a `.env` file or your shell.

| Variable | Description | Default |
| :--- | :--- | :--- |
| `AGENT_URL` | URL of the Agent API | `http://localhost:8000` |
| `OPENAI_API_KEY` | Required for semantic checks (LLM-based assertions) | None |

## Scenario Definition (`scenarios.yaml`)

Scenarios are defined in YAML format. Each scenario consists of a series of "turns" (User input -> Expected Agent output).

```yaml
- id: example_test_01
  tags: ["basic"]
  description: "Test description"
  turns:
    - role: user
      content: "Hello"
    - expected:
        type: text_match
        keyword: "Hello"
```

### Assertion Types

- `text_match`: Checks if the response contains a specific keyword.
- `tool_call`: Verifies that a specific tool was called with optional argument matching.
- `semantic_check`: Uses an LLM to verify if the response meets a natural language instruction (requires `OPENAI_API_KEY`).

## Reporting

After running the tests, a report is generated:

1.  **Console Output**: Real-time progress and a summary table.
2.  **Markdown Report**: `evaluation_report.md` is created in the `evaluation` directory, containing detailed logs of failures and manual checks.

## Troubleshooting

- **Connection Error**: Ensure the agent Docker container is running and accessible at `AGENT_URL`.
- **Semantic Check Skipped**: Ensure `OPENAI_API_KEY` is set if you want to run semantic assertions.
- **Enforcer Blocking**: If tests fail with `[ENFORCER_BLOCKED]`, it means the agent is in Enforcer Mode and the test scenario might not be following the required Plan -> Execute workflow.
