# DAK CLI

Command-line interface for interacting with the Decentralized Agent Kit (DAK) agent.

## Features

- **Single Query Mode**: Send a one-off query and get a response
- **Interactive Chat Mode**: Continuous conversation with the agent
- **Session Management**: Automatic session management for chat history
- **MCP Tool Support**: Agent can use MCP tools transparently

## Installation

### Via uv (Recommended)

```bash
cd cli
uv sync
```

### Via pip

```bash
cd cli
pip install -e .
```

## Configuration

The CLI connects to the DAK agent via HTTP.

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_URL` | `http://localhost:8000` | Agent API URL |
| `USER_ID` | `admin` | User ID for requests |

**Config File**: `~/.dak/config.toml` (optional)

```toml
agent_url = "http://localhost:8000"
user_id = "admin"
```

## Usage

### Single Query Mode

Send a single query and exit:

```bash
uv run dak-cli run "What is the meaning of life?"
```

Example with MCP tool:

```bash
uv run dak-cli run "Use deep_think to analyze consciousness"
```

### Interactive Chat Mode

Start an interactive chat session:

```bash
uv run dak-cli chat
```

Commands in chat mode:

- `/exit` or `/quit`: Exit the chat
- `/clear`: Clear the screen
- `/help`: Show help message
- Any other input: Send to the agent

### Example Session

```bash
$ uv run dak-cli chat
DAK CLI - Chat Mode
Type '/exit' to quit, '/help' for help
───────────────────────────────────────

You: Hello!
Agent: Hello! How can I help you today?

You: Use deep_think to analyze AI
Agent: Based on the DeepThink analysis...
1. Analyzing context...
2. Identifying key variables...
3. Simulating outcomes...
4. Conclusion: This is a complex topic...

You: /exit
Goodbye!
```

## Authentication

The CLI sends requests with the configured `user_id`:

```bash
# Use custom user ID
AGENT_URL=http://localhost:8000 USER_ID=myuser uv run dak-cli run "Hello"
```

For production with authentication:

```bash
# Generate JWT token from UI or auth service
TOKEN="your_jwt_token"

# Not yet implemented - future enhancement
# uv run dak-cli run "Hello" --token "$TOKEN"
```

## Development

### Project Structure

```
cli/
├── src/
│   ├── __init__.py
│   ├── main.py         # CLI entry point
│   ├── client.py       # HTTP client for agent API
│   └── config.py       # Configuration management
├── pyproject.toml      # Project dependencies
└── README.md           # This file
```

### Running from Source

```bash
cd cli
uv sync
uv run python -m src.main run "Hello"
uv run python -m src.main chat
```

## Troubleshooting

### "Connection refused" Error

**Cause**: Agent service is not running or not reachable

**Solution**:
```bash
# Check if agent is running
docker compose ps agent

# Start agent if not running
docker compose up -d agent

# Verify agent is accessible
curl http://localhost:8000/
```

### Slow Responses

**Cause**: LLM is processing or MCP tools are being used

**Expected Behavior**: Responses may take 5-30 seconds depending on:
- LLM provider latency
- Tool execution time
- Query complexity

### MCP Tools Not Working

**Symptom**: Agent doesn't use tools or gives generic responses

**Debugging**:
```bash
# Check MCP server is running
docker compose ps mcp-server

# Check agent logs for MCP connection
docker compose logs agent | grep MCP

# If "MCPClient Error", restart both services
docker compose restart agent mcp-server
```

## Advanced Usage

### Custom Agent URL

```bash
# Connect to remote agent
AGENT_URL=https://my-dak-agent.example.com uv run dak-cli run "Hello"
```

### Scripting

```bash
#!/bin/bash
# example_script.sh

# Process multiple queries
queries=(
  "What is AI?"
  "Use deep_think to analyze machine learning"
  "Explain neural networks"
)

for query in "${queries[@]}"; do
  echo "Query: $query"
  uv run dak-cli run "$query"
  echo "---"
done
```

### Session Management

Each `chat` session creates a unique session ID. To reuse sessions (future enhancement):

```bash
# Not yet implemented
# uv run dak-cli chat --session my-session-id
```

## See Also

- [Agent Documentation](../agent/README.md)
- [MCP Integration Guide](../docs/guides/mcp_integration.md)
- [Docker Deployment Guide](../docs/getting-started/docker_deployment.md)

### Chat

```bash
uv run dak-cli chat

### Run Single Command

```bash
uv run dak-cli run "Hello"
```
