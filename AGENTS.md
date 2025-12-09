# AGENTS.md

> [!NOTE]
> This file is intended for AI coding agents (Coding LLMs). It provides context, architectural guidelines, and commands necessary to work on the `Decentralized-Agent-Kit` repository.

## Project Overview

**Decentralized-Agent-Kit** is a P2P AI Agent ecosystem MVP (Minimum Viable Product) based on the "A2A (Agent-to-Agent)" and "MCP (Model Context Protocol)" concepts.
The core philosophy is **"Loosely Coupled"** and **"Independent Containers"**. Each component (Agent, MCP Server, UI, CLI) runs as an independent Docker container and communicates only via standard protocols.

## Core Philosophy & Architecture

*   **Independent Containers**: Each component must be able to run independently.
*   **Loosely Coupled**: Dependencies are minimized. Communication is via MCP, HTTP/REST, or A2A.
*   **Protocol-First**: Respect interfaces (API, Protocol). Do not rely on internal implementations of other containers.

### Directory Structure & Components

| Directory | Component | Role | Tech Stack |
| :--- | :--- | :--- | :--- |
| `/agent` | **Agent** | AI Brain. Reasoning, planning, memory, A2A protocol. | Python, LangChain/LangGraph, Docker |
| `/mcp-server` | **MCP Server** | Tools & Resources provider (stateless). | Python, MCP SDK, Docker |
| `/ui` | **UI** | User Interface. Chat & Settings. | TypeScript, Next.js, Tailwind CSS |
| `/cli` | **CLI** | Command Line Interface. Dev & Headless ops. | Python, Click/Typer |
| `/db` | **Database** | Persistence layer. | PostgreSQL / FerretDB |

## Build & Test Commands

### Global
*   **Run all services**: `docker compose up --build`
*   **Stop all services**: `docker compose down`

### Agent (`/agent`)
*   **Dependency Management**: `uv sync`
*   **Run Tests**: `uv run pytest`

### CLI (`/cli`)
*   **Dependency Management**: `uv sync`
*   **Run Tool**: `uv run dak-cli [COMMAND]`
*   **Run Tests**: `uv run pytest`
*   **Key Commands**:
    *   `chat`: Start an interactive chat session with the agent.
    *   `config`: Manage configuration settings.

### UI (`/ui`)
*   **Install Dependencies**: `npm install`
*   **Run Dev Server**: `npm run dev`
*   **Build**: `npm run build`

## Development Guidelines

### General Rules
1.  **Docker First**: Assume execution in `docker-compose`.
2.  **Python**: Use `uv` for dependency management. Do not use `pip` directly.
3.  **Configuration**: Use `.env` files. Never hardcode secrets.

### Component-Specific Guidelines

#### Agent
*   **Do**: Implement reasoning and planning logic.
*   **Don't**: Hardcode tool logic. Always use MCP tools.

#### MCP Server
*   **Do**: Provide atomic, stateless tools.
*   **Don't**: Manage complex state (delegate to Agent/DB).

#### CLI
*   **Do**: Provide a robust interface for developers and headless operation.
*   **Structure**:
    *   `src/main.py`: Entry point.
    *   `src/commands/`: Command implementations (e.g., `chat.py`, `config.py`).
    *   `src/client/`: API client to communicate with Agent/MCP.
*   **Note**: The CLI acts as a client to the Agent, similar to the UI. It should not directly import Agent code but communicate via API/Socket.

#### UI
*   **Do**: Focus on UX/UI.
*   **Don't**: Implement business logic that belongs in the Agent.
