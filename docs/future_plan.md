# Future Plan: Towards a Decentralized Agent Ecosystem

This document outlines the gap analysis between the current "Decentralized Agent Kit (DAK)" baseline implementation and the long-term vision described in the [Zenn Book: P2P Agent Ecosystem](https://zenn.dev/teeppp/books/a2a_mcp_system).

## Current Status vs. Vision

| Feature Area | Current Baseline (MVP) | Vision (Zenn Book) | Gap Status |
| :--- | :--- | :--- | :--- |
| **Agent Core** | Single Python Service (`DAKAgent`) | Personal & Shared Agents, distinct roles | ⚠️ Partial |
| **MCP Integration** | Server exists (`mcp-server`), but Agent **cannot use it** | Agent actively queries MCP to use tools/knowledge | 🔴 **Critical** |
| **A2A Protocol** | Simple API Endpoint (`/task/send`) | Standardized protocol, negotiation, discovery | 🟠 Major |
| **Discovery** | Static Configuration (`localhost`) | Dynamic P2P Registry, Blockchain-based | 🔴 Missing |
| **Storage** | MongoDB/FerretDB (Local) | Personal vs. Shared Data separation | ⚠️ Partial |
| **Security** | Basic Auth (JWT/Header) | Trust scoring, Code signing, Sandboxing | 🔴 Missing |

## Gap Analysis & Missing Features

### 1. MCP Client Integration (Critical)
**Current:** The `mcp-server` service is running, but the `DAKAgent` has no logic to connect to it, list tools, or execute them. The agent relies solely on the LLM's internal knowledge.
**Missing:**
- MCP Client implementation within `DAKAgent`.
- Logic to inject MCP tool definitions into the LLM system prompt.
- Logic to execute tools requested by the LLM and return results.

### 2. True A2A Protocol
**Current:** A simple HTTP POST endpoint (`/task/send`) that accepts a text prompt.
**Missing:**
- **Capability Discovery:** Asking another agent "What can you do?".
- **Negotiation:** "I can do this task for X cost/time".
- **Standardized Schema:** Adopting the official A2A protocol specs (once released/finalized).

### 3. Decentralized Registry & Discovery
**Current:** Agents must know each other's URLs (hardcoded in `docker-compose` or config).
**Missing:**
- **Registry Service:** A place to register Agent IDs and endpoints.
- **Discovery Mechanism:** Ability to search for "Translation Agent" and get an endpoint.
- **Trust System:** Verifying if a discovered agent is safe.

### 4. Personal vs. Shared Architecture
**Current:** One monolithic "Agent" service.
**Missing:**
- **Configuration Profiles:** Easy toggle between "Personal Mode" (uses local MCP) and "Shared Mode" (uses public MCP).
- **Multi-MCP Support:** Connecting to multiple MCP servers simultaneously (e.g., Local + Company Shared).

## Future Roadmap

### Phase 1: The "Tool-Using" Agent (Next Step)
Focus: Making the agent actually useful by connecting it to MCP.
- [ ] Implement **MCP Client** in `DAKAgent`.
- [ ] Connect Agent to the local `mcp-server`.
- [ ] Verify the agent can use a simple tool (e.g., "Get Weather" or "Read File").

### Phase 2: The "Collaborative" Agent
Focus: Enhancing Agent-to-Agent interaction.
- [ ] Implement **A2A Capability Discovery** endpoint.
- [ ] Create a second "Shared Agent" service in Docker Compose to test interaction.
- [ ] Implement a "Router" capability: Agent A delegates a task to Agent B based on capability.

### Phase 3: The "Decentralized" Ecosystem
Focus: Discovery and Trust.
- [ ] Implement a simple **Registry Server** (or smart contract).
- [ ] Implement **Dynamic Discovery** in the CLI and Agent.
- [ ] Add **Trust Scoring** logic (allow/deny lists).

### Phase 4: Enterprise & Production
Focus: Security and Scale.
- [ ] **Sandboxing:** Run MCP tools in isolated environments (Docker/WASM).
- [ ] **Fine-grained Auth:** OAuth2 scopes for A2A tasks.
- [ ] **Observability:** Distributed tracing for A2A tasks.
