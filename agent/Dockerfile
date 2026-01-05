FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --no-install-project

# Copy agent definition
COPY dak_agent ./dak_agent
COPY skills ./skills
COPY agent_config.yaml ./agent_config.yaml
COPY README.md .
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Install project
RUN uv sync

# Expose port
EXPOSE 8000

# Use entrypoint to dynamically generate agent.json from AGENT_PUBLIC_URL
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "adk", "web", "--host", "0.0.0.0", "--a2a", "--allow_origins", "http://localhost:3000", "--session_service_uri", "postgresql://username:password@postgres:5432/postgres"]
