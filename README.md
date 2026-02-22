# LAS: langgraph-agentic-scaffold

<img width="3407" height="2072" alt="LangGraph Agentic Scaffold Architecture Diagram" src="https://github.com/user-attachments/assets/a54e5b79-281f-470b-a0e8-a446b1f205b1" />

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A Python orchestration framework for multi-model agentic workflows with structural safety constraints. LAS routes intent through independently-developed capability modules — each a self-contained service with its own UI and development cycle — composed at runtime through MCP.

### Video Briefings

| 5-Minute Developer Briefing | 90-Second Elevator Pitch |
| :---: | :---: |
| [![Watch the 5-Minute Briefing](https://github.com/user-attachments/assets/0bf289cf-da47-48d5-b0b9-ce54fd72486d)](https://www.youtube.com/watch?v=KfqKRXvznDc) | [![Listen to the 90-Second Pitch](https://github.com/user-attachments/assets/155d60bc-be1c-4508-a46c-341bdebfd69c)](http://reflectiveattention.ai/videos/Unlocking_Multi-Agent_AI__Elevator_Pitch_for_the_Langgraph-Agen.mp4) |
| A complete technical rundown of the scaffold's architecture, mission, and how to get started. | A concise, audio-only overview of the project's value proposition. |

---

## What LAS Does

LAS is a **nervous system** that routes user intent through specialized agents, each backed by whichever LLM is best suited to the task. It enforces safety through structure — not by trusting models to behave, but by making it architecturally impossible for them to misbehave.

**Core thesis:** LLMs are unreliable and potentially manipulative. Every specialist executes inside a safety wrapper (SafeExecutor). No specialist can unilaterally terminate, corrupt state, or bypass the control plane. Multi-model adversarial validation catches correlated errors.

### The Computing Metaphor

LAS applies computing primitives to LLM orchestration:

| Concept | LAS Equivalent | Purpose |
|---------|----------------|---------|
| CPU / Scheduler | **Router** | Turn-by-turn routing decisions |
| Stack | **Context Window** | Ephemeral per-invocation working memory |
| Heap | **Artifacts** | Persistent, cross-specialist shared state |
| System Calls | **MCP** | Synchronous service invocation |
| Process Fork | **fork()** | Context-isolated subtask with own lifecycle |

### Explicit Mixture-of-Experts

LAS specialist routing is a visible, auditable version of what happens implicitly inside a transformer's MoE layers. The Router is the gating function. Specialists are the experts. Every routing decision is observable, loggable, and adjustable — unlike implicit MoE where expert selection happens in hidden dimensions.

---

## Ecosystem

LAS is the composition layer for an ecosystem of independently-developed AI services. Each is a self-contained project with its own UI, tests, and development lifecycle:

| Service | Role |
|---------|------|
| **[prompt-prix](https://github.com/shanevcantwell/prompt-prix)** | LLM interface + eval platform. LAS never calls LLMs directly — prompt-prix owns the model boundary via `react_step` MCP. Also provides battery evaluation, model tournament, and a Gradio eval UI. |
| **[semantic-chunker](https://github.com/shanevcantwell/semantic-chunker)** | Embedding infrastructure. embeddinggemma-300m (768-d) and NV-Embed-v2 (4096-d). Provides drift measurement, document classification, and variant analysis for prompt geometry research. |
| **[surf-mcp](https://github.com/shanevcantwell/surf-mcp)** | Browser automation with Fara visual grounding. Perception layer for web interaction. |
| **[local-inference-pool](https://github.com/shanevcantwell/local-inference-pool)** | Multi-GPU compute substrate. Routes model requests across GPUs with JIT-swap guard and least-loaded balancing. |
| **[it-tools-mcp](https://github.com/shanevcantwell/it-tools-mcp)** | 119 IT utility tools. Standard library for data transformation and analysis. |

Repo boundaries are **context firewalls** — separate repos prevent AI assistants from accidentally growing or damaging code that exceeds their context window.

---

## Capabilities

### Context Engineering Pipeline
Every request flows through a structured entry pipeline before reaching specialists:
```
User Request → Triage (classify) → Systems Architect (plan) → Facilitator (assemble context) → Router (route)
```
Specialists don't fetch context — they receive it. The Facilitator is the single point of context assembly, rebuilt fresh each invocation.

### Autonomous Multi-Step Execution
The **Project Director** runs ReAct loops of up to 50 iterations via prompt-prix MCP, with access to filesystem, terminal, web search, and recursive **fork()** for context-isolated subtasks. Live progress publishes to the web UI after every tool call — no more waiting 35 minutes for a single node to complete.

### fork() — Context Garbage Collection
`fork()` spawns a child LAS invocation with its own context window. The child does work, returns a concise result. Parent grows by result size, not work size. Features:
- **Conditioning frame** — anti-fabrication prompt that makes honest failure reports as valued as task completion
- **Expected artifacts** — structured result extraction via named keys
- **Bidirectional archive linkage** — drill down from parent to child or climb up from child to parent

### Tiered Chat with Adversarial Validation
Parallel execution of two specialists backed by different model providers. A synthesizer combines perspectives. Different providers reduce correlated errors — if both models agree, the agreement is more meaningful.

### Real-Time Observability (V.E.G.A.S. Terminal)
A streaming web UI with:
- **Thought Stream** — semantic entries (ROUTE, MCP, FORK, THINK, ARTIFACT) as they happen
- **Intra-node progress** — tool-by-tool updates during long ReAct loops via polling
- **Fork breadcrumbs** — child routing paths and run IDs for cross-referencing
- **Inspector** — prompt viewer, tool chain replay, scratchpad state
- **Archives** — every workflow produces an atomic zip with manifest, traces, and final state

### Multi-Model, Multi-Provider
20+ models supported out of the box. All model bindings are runtime configuration — develop with local models, deploy with cloud APIs, no code changes. Adapters for LM Studio (local GPU pool), Gemini, Anthropic, OpenAI.

### Structural Safety
- **SafeExecutor** wraps all specialist execution — invariant checking, error isolation, circuit breakers
- **Fail-fast validation** — connectivity checks at startup, route validation at build time
- **Four-stage termination** — specialist → signal processor → exit interview → archiver. No unilateral exits.
- **Stagnation detection** — cycle detection catches repeating tool call patterns
- **Invariant monitor** — detects state corruption and routing loops

---

## Security Warning

This scaffold grants significant power to LLMs that you configure as specialists. The tools you create can execute real code, access your filesystem, and make external API calls with your keys.

> **You are granting the configured LLM direct control over these powerful tools.**
>
> An agentic system can create feedback loops that **amplify** a simple misunderstanding over many iterations. This emergent behavior can lead to complex, unintended, and irreversible actions like file deletion or data exposure.
>
> **Always run this project in a secure, sandboxed environment (like a Docker container or a dedicated VM).**

---

## Getting Started with Docker (Recommended)

Docker provides a secure, sandboxed environment and guarantees consistent setup.

### Prerequisites
- Docker and Docker Compose

### Installation

1. **Clone the Repository**
    ```bash
    git clone https://github.com/shanevcantwell/langgraph-agentic-scaffold.git
    cd langgraph-agentic-scaffold
    ```

2. **Configure Your Environment**
    - Copy environment files: `cp .env.example .env`
    - Edit `.env` to add your API keys (e.g., `GOOGLE_API_KEY`, `LANGSMITH_API_KEY`)
    - For local model servers (LM Studio, Ollama), use `host.docker.internal`:
      ```dotenv
      LMSTUDIO_BASE_URL="http://host.docker.internal:1234/v1/"
      NO_PROXY=localhost,127.0.0.1,host.docker.internal
      ```
    - Copy proxy config: `cp proxy/squid.conf.example proxy/squid.conf`
    - Copy user settings: `cp user_settings.yaml.example user_settings.yaml`
    - Edit `user_settings.yaml` to bind models to specialists

3. **Build and Run**
    ```bash
    docker compose up --build -d
    ```

### Interfaces

| Interface | URL | Purpose |
|-----------|-----|---------|
| **V.E.G.A.S. Terminal** | `http://localhost:3000` | Real-time streaming UI with Thought Stream, Inspector, and fork breadcrumbs |
| **API Docs** | `http://localhost:8000/docs` | Interactive FastAPI documentation |
| **CLI** | `docker compose exec app python -m app.src.cli` | Command-line interaction |

### Configuration Changes

- **Python code, `.env`, `config.yaml`:** Restart with `docker compose restart app` (uvicorn --reload handles most Python changes automatically)
- **Proxy config:** `docker compose restart proxy`
- **Dockerfile / pyproject.toml:** Full rebuild with `docker compose up --build -d`

---

## Local Setup (Alternative)

### Prerequisites
- Python 3.12+

### Installation
1. Run the install script: `./scripts/install.sh`
2. Edit `.env` with your API keys
3. Edit `user_settings.yaml` with model bindings

### Running
```bash
# Start API server
./scripts/server.sh start

# Start V.E.G.A.S. Terminal (separate terminal)
cd app/web-ui && npm start
```

---

## Architecture

### Three-Tiered Configuration
```
.env              → Secrets (API keys, never committed)
config.yaml       → Structure (specialists, providers, MCP definitions)
user_settings.yaml → Bindings (which model for which specialist)
```

### Specialist Categories

| Category | Count | Examples |
|----------|-------|---------|
| Core Infrastructure | 6 | Router, Triage, SystemsArchitect, End, Archiver |
| Context Engineering | 3 | Facilitator, ExitInterview, SignalProcessor |
| Autonomous Agents | 1 | ProjectDirector (ReAct + fork) |
| Analysis | 1 | TextAnalysisSpecialist (semantic-chunker + it-tools) |
| Chat & Response | 6 | Tiered chat progenitors, synthesizer, summarizer |
| Generation | 2 | WebBuilder, Critic |
| Browser | 1 | NavigatorBrowserSpecialist (surf-mcp) |

### Test Coverage
- **1,150+ tests** across unit, integration, contract, and concurrent invocation testing
- Unit tests run from host or Docker; integration tests require Docker (live LLM calls)
- Archives in `./logs/archive/` are ground truth for what executed

See [Architecture Reference](./docs/ARCHITECTURE.md) for full technical detail.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture Reference](./docs/ARCHITECTURE.md) | Core concepts, patterns, ecosystem, research connections |
| [Web UI Guide](./docs/WEB_UI.md) | V.E.G.A.S. Terminal layout, data flow, event handling |
| [Configuration Guide](./docs/CONFIGURATION_GUIDE.md) | Three-tiered configuration system |
| [Developer's Guide](./docs/DEVELOPERS_GUIDE.md) | Central hub for all documentation |
| [MCP Guide](./docs/MCP_GUIDE.md) | Message-Centric Protocol integration |
| [Specialist Briefings](./docs/specialists/) | Per-specialist technical deep dives |
| [ADRs](./docs/ADRs/) | Architectural decisions and design rationale |

---

## Research Directions

LAS serves as a workbench for studying how orchestration-layer interventions shape model behavior without touching weights:

- **Prompt geometry** — semantic-chunker measures phrasing geometry in embedding space. RLHF shapes response space by making regions "cold." Phrasings geometrically distant from trained forms may hit unexplored regions — measuring this enables optimization without changing model weights.
- **Explicit MoE as interpretability** — specialist routing decisions are observable analogs of implicit MoE expert selection. LAS makes the gating function visible where TransformerLens can compare it with internal expert routing.
- **Context engineering as physics** — token positions create query-key geometries that determine inference trajectories. The Facilitator constructs the experiential reality for each inference pass.
- **Semantic contrast** — prompt decision-point quality measured via embedding-space drift between branches. Higher pairwise drift → sharper model decision boundaries.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

(c) 2025-2026 [Reflective Attention](http://reflectiveattention.ai/)
