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
# Required: Google API Key for Gemini
GOOGLE_API_KEY=your_google_api_key_here

# Required: NextAuth Secret (generate with: openssl rand -base64 32)
NEXTAUTH_SECRET=your_nextauth_secret_here

# Optional: OAuth Providers
GOOGLE_CLIENT_ID=your_google_oauth_client_id
GOOGLE_CLIENT_SECRET=your_google_oauth_client_secret

# Optional: Alternative LLM Providers
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
- **UI** (port 3000): Next.js web interface
- **PostgreSQL** (port 5432): Database for conversation history

### 4. Verify Deployment

Check all services are running:

```bash
docker compose ps
```

Expected output:
```
NAME                                      STATUS
decentralized-agent-kit-agent-1          Up
decentralized-agent-kit-mcp-server-1     Up
decentralized-agent-kit-postgres-1       Up
decentralized-agent-kit-ui-1             Up
```

### 5. Access the Application

- **Web UI**: http://localhost:3000
- **Agent API**: http://localhost:8000
- **MCP Server**: http://localhost:8001

## Service Details

### Agent Service

**Container**: `decentralized-agent-kit-agent-1`  
**Port**: `8000`  
**Health Check**: `http://localhost:8000/`

**Responsibilities**:
- Main LLM interaction
- MCP Client for tool discovery/execution
- State management with PostgreSQL
- A2A (Agent-to-Agent) protocol handler

**Logs**:
```bash
docker compose logs agent -f
```

### MCP Server

**Container**: `decentralized-agent-kit-mcp-server-1`  
**Port**: `8001` (mapped from internal 8000)  
**Health Check**: `http://localhost:8001/mcp`

**Responsibilities**:
- Expose tools via MCP protocol
- Handle tool execution requests

**Logs**:
```bash
docker compose logs mcp-server -f
```

### UI Service

**Container**: `decentralized-agent-kit-ui-1`  
**Port**: `3000`  
**Health Check**: `http://localhost:3000/`

**Responsibilities**:
- Web interface for agent interaction
- NextAuth.js authentication
- Chat history display

**Logs**:
```bash
docker compose logs ui -f
```

## Configuration

### Environment Variables

#### Agent Service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes* | - | Google Gemini API key |
| `OPENAI_API_KEY` | Yes* | - | OpenAI API key |
| `ANTHROPIC_API_KEY` | Yes* | - | Anthropic API key |
| `GEMINI_MODEL` | No | `gemini-3-pro-preview` | Gemini model name |
| `LLM_PROVIDER` | No | `gemini` | LLM provider (`gemini`, `openai`, `anthropic`) |
| `DATABASE_URL` | No | Auto-configured | PostgreSQL connection string |
| `MCP_SERVER_URL` | No | `http://mcp-server:8000/mcp` | MCP Server URL |
| `ENABLE_ENFORCER_MODE` | No | `false` | Enable strict ReAct pattern |
| `LANGFUSE_PUBLIC_KEY` | No | - | LangFuse Public Key |
| `LANGFUSE_SECRET_KEY` | No | - | LangFuse Secret Key |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | LangFuse Host |

*At least one LLM provider API key is required

#### UI Service

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXTAUTH_SECRET` | Yes | - | NextAuth.js secret (32+ chars) |
| `NEXTAUTH_URL` | No | `http://localhost:3000` | App URL |
| `NEXT_PUBLIC_AGENT_URL` | No | `http://localhost:8000` | Agent API URL |
| `NEXT_PUBLIC_REQUIRE_AUTH` | No | `false` | Require authentication |
| `GOOGLE_CLIENT_ID` | No | - | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | No | - | Google OAuth secret |

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
docker compose logs ui -f
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

# Agent will fall back to in-memory state manager
```

### UI Can't Connect to Agent

**Symptoms**: 500 errors or CORS issues in browser console

**Solution**:
1. Verify `NEXT_PUBLIC_AGENT_URL` in `.env`
2. Check agent CORS configuration in `agent/src/main.py`
3. Restart both services:
   ```bash
   docker compose restart agent ui
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

- [ ] Change `NEXTAUTH_SECRET` to a strong random value
- [ ] Use HTTPS with proper SSL certificates
- [ ] Set `NEXT_PUBLIC_REQUIRE_AUTH=true`
- [ ] Configure OAuth providers with production URLs
- [ ] Restrict CORS origins in `agent/src/main.py`
- [ ] Use strong database passwords
- [ ] Enable Docker secrets for sensitive values
- [ ] Set up regular database backups
- [ ] Configure log rotation
- [ ] Implement rate limiting

### Scaling

**Horizontal Scaling**:
```yaml
services:
  agent:
    deploy:
      replicas: 3
```

**External Database**:
Replace PostgreSQL with a managed PostgreSQL service (e.g., AWS RDS, Google Cloud SQL).

### Monitoring

**Health Checks**:
```bash
curl http://localhost:8000/
curl http://localhost:8001/mcp
curl http://localhost:3000/
```

**Resource Usage**:
```bash
docker stats
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [MCP Integration Guide](../guides/mcp_integration.md)
- [CLI Usage Guide](../guides/cli_usage.md)
