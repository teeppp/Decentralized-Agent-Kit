# Docker Deployment Guide

This guide covers deploying the Decentralized Agent Kit using Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose V2
- At least 4GB of free RAM
- Git

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Decentralized-Agent-Kit.git
cd Decentralized-Agent-Kit
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and configure required variables:

```bash
# Required: API key matching MODEL_NAME (Gemini by default)
GOOGLE_API_KEY=your_google_api_key_here

# Optional: Alternative LLM providers
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

### 3. Build and Start Services

```bash
docker compose up --build -d
```

This will start:
- **Agent** (port 8000): Main DAK agent with LLM integration
- **MCP Server** (port 8001): Tool server for MCP protocol
- **BFF UI** (port 8002): FastAPI + HTMX web interface
- **PostgreSQL** (port 5432): Database for conversation history

Ollama (local LLM) is optional: `docker compose --profile local-llm up -d`.

### 4. Verify Deployment

Check all services are running:

```bash
docker compose ps
```

Expected output:
```
NAME                                      STATUS
decentralized-agent-kit-agent-1          Up
decentralized-agent-kit-bff-1            Up
decentralized-agent-kit-mcp-server-1     Up
decentralized-agent-kit-postgres-1       Up
```

### 5. Access the Application

- **Web UI (BFF)**: http://localhost:8002
- **Agent API**: http://localhost:8000
- **MCP Server**: http://localhost:8001

## Service Details

### Agent Service

**Container**: `decentralized-agent-kit-agent-1`
**Port**: `8000`
**Health Check**: `http://localhost:8000/list-apps`

**Responsibilities**:
- Main LLM interaction (via LiteLLM)
- MCP Client for tool discovery/execution
- Agent Skills (SKILL.md) loading
- State management with PostgreSQL
- A2A (Agent-to-Agent) protocol handler

**Logs**:
```bash
docker compose logs agent -f
```

### MCP Server

**Container**: `decentralized-agent-kit-mcp-server-1`
**Port**: `8001` (mapped from internal 8000)
**Endpoint**: `http://localhost:8001/mcp`

**Responsibilities**:
- Expose tools via MCP protocol (streamable HTTP)
- Handle tool execution requests against the mounted `/projects` workspace

**Logs**:
```bash
docker compose logs mcp-server -f
```

### BFF UI Service

**Container**: `decentralized-agent-kit-bff-1`
**Port**: `8002` (mapped from internal 8000)
**Health Check**: `http://localhost:8002/`

**Responsibilities**:
- Web chat interface for agent interaction (FastAPI + HTMX)
- Renders agent tool calls as a "thinking process" view

**Logs**:
```bash
docker compose logs bff -f
```

## Configuration

### Environment Variables (Agent)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes* | - | Google Gemini API key |
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes* | - | Anthropic API key |
| `MODEL_NAME` | No | `gemini-2.5-flash` | LiteLLM model name |
| `DATABASE_URL` | No | Auto-configured | PostgreSQL connection string |
| `MCP_SERVER_URL` | No | `http://mcp-server:8000/mcp` | Default MCP server URL |
| `ENABLE_ENFORCER_MODE` | No | `false` | Enable strict ReAct pattern (Ulysses Pact) |
| `ENABLE_AP2_PROTOCOL` | No | `false` | Enable agent-to-agent payments (experimental) |
| `SOLANA_USE_MOCK` | No | `true` | Mock Solana wallet (no real transactions) |
| `AGENT_SKILLS_DIRS` | No | `/app/skills` | Colon-separated skill directories |
| `LANGFUSE_PUBLIC_KEY` | No | - | LangFuse Public Key |
| `LANGFUSE_SECRET_KEY` | No | - | LangFuse Secret Key |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | LangFuse Host |

*At least one LLM provider API key is required

Additional MCP servers and A2A peers are configured in `agent/agent_config.yaml`
(mounted into the container by docker-compose).

### Volume Mounts

```yaml
volumes:
  postgres_data:    # PostgreSQL database
```

**Persistence**: Agent conversation history and state are persisted in these volumes.

**Backup**:
```bash
docker compose down
docker run --rm -v decentralized-agent-kit_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

## Management Commands

### View Logs

All services:
```bash
docker compose logs -f
```

Specific service:
```bash
docker compose logs agent -f
docker compose logs mcp-server -f
docker compose logs bff -f
```

### Restart Services

All services:
```bash
docker compose restart
```

Specific service:
```bash
docker compose restart agent
docker compose restart mcp-server
```

### Stop Services

```bash
docker compose down
```

With volume cleanup:
```bash
docker compose down -v
```

### Rebuild After Code Changes

```bash
docker compose up --build -d
```

Rebuild specific service:
```bash
docker compose up --build -d agent
```

### Shell Access

```bash
docker compose exec agent bash
docker compose exec mcp-server bash
```

## Integration Testing (no API keys)

The full stack can run against a deterministic fake LLM:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
cd tests/integration && uv run pytest
docker compose -f docker-compose.yml -f docker-compose.test.yml down -v
```

## Troubleshooting

### Service Won't Start

**Check logs**:
```bash
docker compose logs <service-name>
```

**Common issues**:
1. Port already in use → Change ports in `docker-compose.yml`
2. Environment variables missing → Check `.env` file
3. Resource limits → Increase Docker memory allocation

### Agent Can't Connect to MCP Server

**Symptoms**: `MCPClient Error listing tools`

**Solution**:
```bash
# Check if mcp-server is running
docker compose ps mcp-server

# Check network connectivity
docker compose exec agent ping mcp-server

# Restart both services
docker compose restart agent mcp-server
```

### Database Connection Issues

**Symptoms**: `Failed to connect to Database`

**Solution**:
```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Restart database service
docker compose restart postgres
```

### BFF Can't Connect to Agent

**Symptoms**: "Session Error" or error bubbles in the chat UI

**Solution**:
1. Verify the agent is healthy: `curl http://localhost:8000/list-apps`
2. Check the BFF's `AGENT_URL` (defaults to `http://agent:8000` in compose)
3. Restart both services:
   ```bash
   docker compose restart agent bff
   ```

### Out of Memory

**Symptoms**: Services crashing or slow performance

**Solution**:
1. Increase Docker memory limit (minimum 4GB)
2. Reduce number of running services
3. Clear unused Docker resources:
   ```bash
   docker system prune -a
   ```

## Production Deployment

### Security Checklist

- [ ] Use HTTPS with proper SSL certificates and an authenticating reverse proxy
- [ ] Use strong database passwords
- [ ] Enable Docker secrets for sensitive values
- [ ] Restrict the MCP server's workspace mount (it executes shell commands)
- [ ] Set up regular database backups
- [ ] Configure log rotation
- [ ] Implement rate limiting

### Scaling

**External Database**:
Replace PostgreSQL with a managed PostgreSQL service (e.g., AWS RDS, Google Cloud SQL).

### Monitoring

**Health Checks**:
```bash
curl http://localhost:8000/list-apps
curl http://localhost:8002/
```

**Resource Usage**:
```bash
docker stats
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [MCP Integration Guide](../guides/mcp_integration.md)
- [CLI Usage Guide](../guides/cli_usage.md)
