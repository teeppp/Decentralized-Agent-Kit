# Decentralized Agent Kit (DAK)

An intelligent agent framework with LLM integration, Model Context Protocol (MCP) tool support, and Agent-to-Agent (A2A) communication capabilities.

## Features

- **Multi-LLM Support**: Gemini, OpenAI, Anthropic, Local LLM (Ollama) via LiteLLM
- **MCP Protocol**: Dynamic tool discovery and execution via Model Context Protocol (multiple servers supported)
- **Agent Skills**: Extend the agent with `SKILL.md`-based skills loaded from one or more directories
- **A2A Protocol**: Agent-to-Agent communication for collaborative workflows
- **Web UI (BFF)**: Lightweight HTMX-based chat interface
- **CLI Tool**: Command-line interface for direct agent interaction
- **Persistent State**: Conversation history with PostgreSQL
- **Enforcer Mode**: Strict ReAct pattern with "Ulysses Pact" for reliability
- **Observability**: OpenTelemetry tracing with LangFuse integration

### Experimental Features

- **AP2 Payment Protocol**: Agent-to-Agent payments with a Solana wallet (mock mode by default). See [Solana Integration](docs/experimental/solana_integration.md).
- **Dynamic Mode Switching**: The agent refreshes its instruction and toolset when the context window fills up or when it decides to switch focus.

## Quick Start with Docker

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/Decentralized-Agent-Kit.git
cd Decentralized-Agent-Kit
cp .env.example .env

# 2. Add your LLM API key to .env
echo "GOOGLE_API_KEY=your_key_here" >> .env

# 3. Start all services
docker compose up --build -d

# 4. Access the application
# Web UI (BFF): http://localhost:8002
# Agent API:    http://localhost:8000
# MCP Server:   http://localhost:8001
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  BFF (UI)   │────▶│  DAK Agent   │────▶│ MCP Server  │
│ FastAPI +   │     │ (google-adk) │     │  (FastMCP)  │
│ HTMX        │     │              │     │             │
│             │     │ • LLM Client │     │ • deep_think│
│  CLI ───────┼────▶│ • Skills     │     │ • file tools│
│             │     │ • MCP Client │     │ • run_cmd   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │ PostgreSQL  │
                    │ (Sessions)  │
                    └─────────────┘
```

## Directory Structure

- **`agent/`**: Python agent service (google-adk based `AdaptiveAgent`, skills, wallet)
- **`mcp-server/`**: Model Context Protocol server for tool execution
- **`bff/`**: HTMX-based web UI (Backend For Frontend pattern)
- **`cli/`**: Command-line tool for agent interaction
- **`tests/integration/`**: Docker-based integration test suite (no API keys required)
- **`docs/`**: Documentation

## Documentation

### Getting Started
- [Docker Deployment Guide](docs/getting-started/docker_deployment.md)
- [Installation & Setup](docs/getting-started/installation.md)
- [Local Authentication Quick Start](docs/getting-started/local_auth.md)

### Guides
- [MCP Integration Guide](docs/guides/mcp_integration.md) - Tool development and usage
- [CLI Usage Guide](docs/guides/cli_usage.md)
- [Enforcer Mode Guide](docs/enforcer_mode.md)
- [Agent Skills Guide](docs/agent_skills.md): Extend the agent with new capabilities
- [Built-in Tools Reference](docs/built_in_tools.md): `list_skills`, `enable_skill`, `switch_mode`, etc.

### Architecture
- [System Overview](docs/architecture/overview.md)
- [BFF Architecture](docs/bff_architecture.md)
- [Chat History Specification](docs/architecture/chat_history.md)
- [Dynamic Mode Switching](docs/dynamic_mode_switching.md)

## Using the CLI

```bash
cd cli
uv sync

# Single query
uv run dak-cli run "What is consciousness?"

# With MCP tool
uv run dak-cli run "Use deep_think to analyze AI ethics"

# Interactive chat
uv run dak-cli chat
```

## Adding MCP Servers

The agent can connect to multiple MCP servers. Edit `agent/agent_config.yaml`:

```yaml
mcp_servers:
  - name: "local-mcp"
    url: "http://mcp-server:8000/mcp"
    type: "http"          # "http" (streamable HTTP) or "sse"
  - name: "my-extra-mcp"
    url: "http://my-extra-mcp:8000/mcp"
    type: "http"
```

Skills can target a specific server with a `mcp_server: <name>` field in their
`SKILL.md` frontmatter; tools without a skill use the default server
(`MCP_SERVER_URL`). When running in Docker, make sure the extra server is
reachable from the `agent` container (add it to `docker-compose.yml` or an
override file).

## Development

### Local Setup (without Docker)

#### Agent Service

```bash
cd agent
uv sync
export GOOGLE_API_KEY=your_key
export MCP_SERVER_URL=http://localhost:8001/mcp
uv run adk web --host 0.0.0.0
```

#### MCP Server

```bash
cd mcp-server
uv sync
uv run python main.py
```

#### BFF UI

```bash
cd bff
uv sync
AGENT_URL=http://localhost:8000 uv run uvicorn main:app --reload --port 8002
```

### Running Tests

Each component has its own unit test suite (no API keys or network required):

```bash
cd agent && uv run pytest        # also: cli, mcp-server, bff
```

Integration tests run the full stack with a deterministic fake LLM
(no API keys required):

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
cd tests/integration && uv run pytest
docker compose -f docker-compose.yml -f docker-compose.test.yml down -v
```

CI runs both suites on every pull request (`.github/workflows/ci.yml`).

## Environment Configuration

Key environment variables (see `.env.example` for full list):

```bash
# LLM Provider (at least one required)
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_key        # optional
ANTHROPIC_API_KEY=your_anthropic_key  # optional

# LLM Configuration
MODEL_NAME=gemini-2.5-flash  # or 'openai/gpt-4o', 'anthropic/claude-...', local model

# Enforcer Mode
ENABLE_ENFORCER_MODE=true    # Enable strict ReAct pattern (Ulysses Pact)

# AP2 Payment Protocol (experimental)
ENABLE_AP2_PROTOCOL=false
SOLANA_USE_MOCK=true         # mock wallet by default

# Agent Skills
AGENT_SKILLS_DIRS=/app/skills:/app/provider_skills  # colon-separated

# LangFuse Monitoring (optional)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Local LLM (Ollama) — start with: docker compose --profile local-llm up
LOCAL_LLM_BASE_URL=http://ollama:11434/v1
LOCAL_LLM_API_KEY=ollama
```

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details.
