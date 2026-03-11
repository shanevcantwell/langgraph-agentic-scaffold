# LAS: langgraph-agentic-scaffold

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Multi-model orchestration with structural safety — an explicit Mixture-of-Experts where the gating is semantic, the experts are heterogeneous, and the kernel enforces invariants they can't bypass.

> **Status:** Active development. Expect breaking changes between alpha releases.

---

## What This Is

LAS is a personal research project that orchestrates multi-model agentic workflows through LangGraph. It routes user intent through specialized agents — each backed by whichever LLM fits the task — while enforcing safety through structure, not trust.

**Core thesis:** LLMs are unreliable. Every specialist executes inside a safety wrapper. No specialist can unilaterally terminate, corrupt state, or bypass the control plane.

### The Computing Metaphor

LAS applies computing primitives to LLM orchestration:

| Concept | LAS Equivalent | Purpose |
|---------|----------------|---------|
| CPU / Scheduler | **Router** | Turn-by-turn semantic routing decisions |
| Stack | **Context Window** | Ephemeral per-invocation working memory |
| Heap | **Artifacts** | Persistent, cross-specialist shared state |
| System Calls | **MCP** | Synchronous service invocation bypassing Router |
| Signals | **signals field** | Asynchronous inter-node communication (replace reducer) |
| Process delegation | **delegate()** | Context-isolated subtask with own lifecycle |

Specialist routing is a visible, auditable version of what happens implicitly inside a transformer's MoE layers. The Router is the gating function. Specialists are the experts. Every routing decision is observable and loggable. See [Agentic Cognates](./docs/ADRs/AGENTIC_COGNATES.md) for the full treatment.

---

## How a Request Flows

Every request passes through a staged investment pipeline before reaching a specialist:

```
User Request → Triage (cost gate) → Systems Architect (plan) → Facilitator (context) → Router (dispatch)
```

**Triage** is a cheap ACCEPT/REJECT classifier. It fires before the system invests an expensive SA planning call. If the request is ambiguous, Triage bounces it back for clarification — zero wasted compute.

**Systems Architect** produces a structured `task_plan` with execution steps and acceptance criteria. If SA fails, the graph routes to END immediately (fail-fast).

**Facilitator** is the sole writer to `gathered_context`. Specialists don't fetch context — they receive it. This is a hard architectural constraint, not a convention. On retry, Facilitator curates prior work into `accumulated_work` so the specialist sees what it did last time without re-reading its own trace (which causes fabrication loops).

**Router** selects a specialist from an enum-constrained menu. Token-level enforcement prevents open-weight models from inventing specialist names. Menu filtering adapts as the workflow progresses — planning specialists disappear after context is gathered, forbidden specialists are removed on loop detection.

---

## Autonomous Execution

The **Project Director** runs ReAct loops via prompt-prix MCP with access to filesystem, terminal, and browser tools. Live progress publishes to the web UI after every tool call.

**Stagnation detection** pattern-matches on tool call signatures — `read(A) → move(A) → read(A) → move(A)` triggers at period 2 repeated 3x. This catches real loops, not just "you've been running too long." Max iterations is the fallback, not the primary safety valve.

**delegate()** spawns a child LAS invocation with its own context window. The child does work, returns a concise result. Parent grows by result size, not work size. A conditioning frame makes honest failure reports as valued as task completion.

**Signal-based completion:** PD writes `completion_signal` on all four exit paths (success, error, stagnation, partial). The Exit Interview reads it and resolves in 0ms — no LLM call needed. The signals field uses a replace reducer, so each write is a complete snapshot with no stale flags leaking across retries.

---

## Governed Termination

No specialist can self-declare "done." Termination flows through four stages:

1. **Specialist** completes and writes a completion signal
2. **Signal Processor** classifies the outcome via a 6-level priority chain (circuit breaker > user abort > max_iterations > stagnation > completion > continuation)
3. **Exit Interview** independently verifies by inspecting filesystem and artifacts — it can't see prior state, only final state
4. **End/Archiver** assembles the user response and produces an atomic archive (manifest, traces, final state)

---

## Multi-Model

Different models for different roles, all runtime-configurable. Router might be Qwen on an RTX-3090, Project Director might be Gemini Pro, chat progenitors might be Gemini + Claude for adversarial validation. No code changes — just `user_settings.yaml`.

Adapters for local inference (LM Studio / llama.cpp), Gemini, Anthropic, and OpenAI. Named server references support distributed inference across multiple GPU machines.

---

## Ecosystem

LAS is the composition layer for independently-developed AI services, each a self-contained project with its own UI and development cycle:

| Service | Role |
|---------|------|
| **[prompt-prix](https://github.com/shanevcantwell/prompt-prix)** | LLM interface + eval platform. LAS never calls LLMs directly — prompt-prix owns the model boundary via `react_step` MCP. |
| **[semantic-chunker](https://github.com/shanevcantwell/semantic-chunker)** | Embedding infrastructure. embeddinggemma-300m (768-d) and NV-Embed-v2 (4096-d). Drift measurement, document classification, variant analysis. |
| **[surf-mcp](https://github.com/shanevcantwell/surf-mcp)** | Browser automation with Fara visual grounding. |
| **[local-inference-pool](https://github.com/shanevcantwell/local-inference-pool)** | Multi-GPU compute substrate with JIT-swap guard and least-loaded balancing. |
| **[it-tools-mcp](https://github.com/shanevcantwell/it-tools-mcp)** | 119 IT utility tools for data transformation and analysis. |

Repo boundaries are **context firewalls** — separate repos prevent AI assistants from accidentally growing or damaging code that exceeds their context window.

---

## Security Warning

> **You are granting LLMs direct control over powerful tools.** The specialists you configure can execute code, access the filesystem, and make external API calls with your keys.
>
> An agentic system can create feedback loops that **amplify** a simple misunderstanding over many iterations into irreversible actions.
>
> **Always run in a sandboxed environment (Docker container or dedicated VM).**

---

## Running It

### Docker (Recommended)

```bash
git clone https://github.com/shanevcantwell/langgraph-agentic-scaffold.git
cd langgraph-agentic-scaffold

cp .env.example .env                          # Add API keys
cp proxy/squid.conf.example proxy/squid.conf
cp user_settings.yaml.example user_settings.yaml  # Bind models to specialists

docker compose up --build -d
```

For local model servers (LM Studio, Ollama), set in `.env`:
```dotenv
LOCAL_INFERENCE_BASE_URL="http://host.docker.internal:1234/v1"
```

| Interface | URL |
|-----------|-----|
| **V.E.G.A.S. Terminal** | `http://localhost:3000` |
| **API** | `http://localhost:8000/v1/chat/completions` |
| **API Docs** | `http://localhost:8000/docs` |

The API is **OpenAI-compatible** — any client that speaks the OpenAI REST protocol (`/v1/chat/completions`) can drive LAS directly. This includes curl, the OpenAI SDK, Continue, or any tool that targets the OpenAI API format.

**Configuration changes:** Python code changes are picked up by uvicorn --reload. Dockerfile or pyproject.toml changes require `docker compose up --build -d`.

### Local (Alternative)

```bash
./scripts/install.sh
# Edit .env and user_settings.yaml, then:
./scripts/server.sh start
```

---

## Observability

Every workflow produces a timestamped archive in `./logs/archive/`:
```
run_YYYYMMDD_HHMMSS_<hash>.zip
├── manifest.json        # routing_history, timestamps, metadata
├── llm_traces.jsonl     # per-specialist execution with latency
├── final_state.json     # accumulated state at workflow end
└── artifacts/           # all produced artifacts
```

The **V.E.G.A.S. Terminal** provides real-time streaming: semantic thought entries, tool-by-tool progress during ReAct loops, delegate() breadcrumbs, and an inspector for prompt replay and scratchpad state.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture Reference](./docs/ARCHITECTURE.md) | Core concepts, patterns, state model |
| [Flow Examples](./docs/FLOWS.md) | Prompt-to-specialist flows with Mermaid diagrams |
| [Configuration Guide](./docs/CONFIGURATION_GUIDE.md) | Three-tiered configuration, distributed inference |
| [Web UI Guide](./docs/WEB_UI.md) | V.E.G.A.S. Terminal layout and data flow |
| [MCP Guide](./docs/MCP_GUIDE.md) | Model Context Protocol integration |
| [Specialist Briefings](./docs/specialists/) | Per-specialist technical deep dives |
| [Developer Docs](./docs/dev/) | Creating specialists, patterns, subgraphs, testing, troubleshooting |
| [ADRs](./docs/ADRs/) | Architectural decisions and design rationale |

---

## Research Directions

LAS serves as a workbench for studying how orchestration-layer interventions shape model behavior without touching weights:

- **Prompt geometry** — semantic-chunker measures phrasing geometry in 768-d embedding space. RLHF shapes response space by making regions "cold." Phrasings distant from trained forms may hit unexplored regions.
- **Explicit MoE as interpretability** — specialist routing decisions are observable analogs of implicit MoE expert selection. TransformerLens can compare external routing with internal expert activation.
- **Context engineering as physics** — token positions create query-key geometries that determine inference trajectories. The Facilitator constructs the experiential reality for each inference pass.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

(c) 2025-2026 [Reflective Attention](http://reflectiveattention.ai/)
