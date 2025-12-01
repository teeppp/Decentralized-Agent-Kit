# Installation & Setup

## Prerequisites

- **Docker & Docker Compose**: Required for running the full stack.
- **Python 3.9+**: Required for local development of Agent and CLI.
- **Node.js 18+**: Required for local development of UI.
- **uv**: Recommended Python package manager.

## Quick Start (Docker)

The easiest way to run DAK is using Docker Compose.

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd Decentralized-Agent-Kit
    ```

2.  **Configure Environment**:
    ```bash
    cp .env.example .env
    # Edit .env to add your API keys (Google Gemini, etc.) and Auth secrets
    ```

3.  **Start Services**:
    ```bash
    docker compose up --build
    ```

4.  **Access UI**:
    Open `http://localhost:3000` in your browser.

## Local Development

### Agent

```bash
cd agent
uv sync
uv run src/main.py
```

### UI

```bash
cd ui
npm install
npm run dev
```

### CLI

```bash
cd cli
uv sync
uv run dak-cli --help
```
