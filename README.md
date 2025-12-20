# Decentralized Agent Kit (DAK)

An intelligent agent framework with LLM integration, Model Context Protocol (MCP) tool support, and Agent-to-Agent (A2A) communication capabilities.

## Features

- **Multi-LLM Support**: Gemini, OpenAI, Anthropic, Local LLM (Ollama)
- **MCP Protocol**: Dynamic tool discovery and execution via Model Context Protocol
- **A2A Protocol**: Agent-to-Agent communication for collaborative workflows
- **Web UI**: Next.js-based chat interface with OAuth authentication
- **CLI Tool**: Command-line interface for direct agent interaction
- **Persistent State**: Conversation history with PostgreSQL
- **Enforcer Mode**: Strict ReAct pattern with "Ulysses Pact" for reliability
- **Observability**: OpenTelemetry tracing with LangFuse integration

## Quick Start with Docker

```bash
# 1. Clone and configure
git clone https://github.com/yourusername/Decentralized-Agent-Kit.git
cd Decentralized-Agent-Kit
cp .env.example .env

# 2. Add your LLM API key to .env
echo "GOOGLE_API_KEY=your_key_here" >> .env
echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env

# 3. Start all services
docker compose up --build -d

# 4. Access the application
# Web UI: http://localhost:3000
# Agent API: http://localhost:8000
# MCP Server: http://localhost:8001
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Web UI    │────▶│  DAK Agent   │────▶│ MCP Server  │
│  (Next.js)  │     │ (google-adk) │     │  (FastMCP)  │
│             │     │              │     │             │
│ • Chat UI   │     │ • LLM Client │     │ • Tools     │
│ • Auth      │     │ • MCP Client │     │ • deep_think│
│             │     │ • State Mgmt │     └─────────────┘
└─────────────┘     └──────────────┘
                           │
                    ┌──────▼──────┐
                    │ PostgreSQL  │
                    │ (History)   │
                    └─────────────┘
```

## Directory Structure

- **`agent/`**: Python-based agent service with LLM and MCP integration
- **`mcp-server/`**: Model Context Protocol server for tool execution
- **`ui/`**: Next.js web interface
- **`cli/`**: Command-line tool for agent interaction
- **`docs/`**: Comprehensive documentation

#### 3. **HTMX-based BFF UI (New)**
A lightweight, Python-based UI using the **BFF (Backend For Frontend)** pattern.
- **URL**: http://localhost:8002
- **Tech Stack**: FastAPI, htmx, Jinja2
- **Docs**: [BFF Architecture](docs/bff_architecture.md)

To run the BFF service:
```bash
docker compose up -d --build bff
```

## Documentation

### Getting Started
- [Docker Deployment Guide](docs/getting-started/docker_deployment.md) 🚀
- [Installation & Setup](docs/getting-started/installation.md)
- [Local Authentication Quick Start](docs/getting-started/local_auth.md)

### Guides
- **[MCP Integration Guide](docs/guides/mcp_integration.md)** - Tool development and usage
- [CLI Usage Guide](docs/guides/cli_usage.md)
- [Authentication Testing](docs/guides/authentication_testing.md)
- [Enforcer Mode Guide](docs/enforcer_mode.md)
- [Agent Skills Guide](docs/agent_skills.md): Learn how to extend the agent with new capabilities.
- [Built-in Tools Reference](docs/built_in_tools.md): Documentation for core tools like `list_skills` and `switch_mode`.

### Architecture
- [System Overview](docs/architecture/overview.md)
- [Chat History Specification](docs/architecture/chat_history.md)
- [Future Roadmap](docs/future_plan.md)

### Service Documentation
- [Agent README](agent/README.md)
- [MCP Server README](mcp-server/README.md)
- [CLI README](cli/README.md)

## Using the CLI

```bash
# Single query
cd cli
uv run dak-cli run "What is consciousness?"

# With MCP tool
uv run dak-cli run "Use deep_think to analyze AI ethics"

# Interactive chat
uv run dak-cli chat
```

## Development

### Local Setup (without Docker)

#### Agent Service

```bash
cd agent
uv sync
export GOOGLE_API_KEY=your_key
uv run uvicorn src.main:app --reload
```

#### MCP Server

```bash
cd mcp-server
uv sync
uv run python main.py
```

#### UI

```bash
cd ui
npm install
npm run dev
```

## Environment Configuration

Key environment variables (see `.env.example` for full list):

```bash
# LLM Provider (at least one required)
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_key  # optional
ANTHROPIC_API_KEY=your_anthropic_key  # optional

# Enforcer Mode
ENABLE_ENFORCER_MODE=true  # Enable strict ReAct pattern

# LangFuse Monitoring (Optional)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# LLM Configuration
MODEL_NAME=gemini-2.5-flash  # or 'gpt-4o', 'claude-3-opus', 'local-model'

# Local LLM (Ollama)
LOCAL_LLM_BASE_URL=http://ollama:11434/v1
LOCAL_LLM_API_KEY=ollama

# NextAuth (for UI)
NEXTAUTH_SECRET=your_secret_here
NEXT_PUBLIC_REQUIRE_AUTH=false  # set to 'true' for production

# OAuth (optional)
GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_secret
```

## License

Apache 2.0 - See [LICENSE](LICENSE) file for details.