# ADR-UI-002: AnythingLLM Integration — LAS as Inference Service

**Status:** Completed
**Date:** 2026-03-03
**Completed:** 2026-04-03
**Context:** LAS UI / API Surface
**Layer:** Presentation + API
**Relates To:** ADR-CORE-068 (Inference-As-Service), ADR-CORE-052 (Adapter-Registry)

---

## Abstract

LAS currently has no general-purpose chat UI. The V.E.G.A.S. Terminal is a task-specific interface for structured agentic workflows, not conversational analysis. AnythingLLM provides a workspace-based UI with threading, RAG, document ingestion, and agent flows — features that would take months to build in-house.

Rather than building a chat UI or exposing LAS as an MCP server, this ADR proposes that **LAS masquerade as one of the inference services AnythingLLM already supports** (OpenAI-compatible). AnythingLLM connects to LAS the same way it connects to LM Studio or Ollama. Users get AnythingLLM's sandbox UI for interactive work; LAS gets a standards-compliant API surface that any OpenAI-compatible client can consume.

---

## Motivation

After 4 months of LAS development, the orchestration layer is mature but the analysis workflows that motivated the project remain inaccessible because:

1. **LM Studio has no API integration path to LAS** — great UI, no way to route through LAS specialists
2. **LAS's API (`/v1/graph/invoke`) is bespoke** — only LAS clients speak it
3. **The llama.cpp stack bugs (LM Studio #1592, #1593, #1589)** make raw local inference unreliable for the multi-turn agentic work LAS was designed for
4. **Interactive analysis work** (cutting/pasting, regenerating, branching conversations) needs a good conversational UI, not a task submission endpoint

AnythingLLM solves this because it's an **orchestration layer**, not an inference engine. It delegates all model calls to configurable backends. If LAS looks like a backend, AnythingLLM becomes LAS's UI for free.

---

## What AnythingLLM Is (and Isn't)

### Architecture: Three Tiers

```
┌─────────────────────────────────────────┐
│   AnythingLLM UI (Desktop/Browser)      │
│  (Chat, Document Upload, Agent Flows)   │
├─────────────────────────────────────────┤
│   AnythingLLM Server (NodeJS Express)   │
│  (Orchestration, Document Processing,   │
│   Vector DB Management, MCP Routing)    │
├─────────────────────────────────────────┤
│   LLM Backends (pluggable)              │
│  - LM Studio (local, OpenAI-compatible) │
│  - Ollama (CLI inference)               │
│  - OpenAI, Anthropic, Gemini (cloud)    │
│                                         │
│   Vector Stores (pluggable)             │
│  - Chroma, Pinecone, Weaviate, etc.     │
│                                         │
│   Embedding Models (pluggable)          │
│  - Local (Ollama), Cloud, HuggingFace   │
└─────────────────────────────────────────┘
```

**Key insight:** Ollama/LM Studio run inference. AnythingLLM orchestrates everything around inference. It is closer to what LAS is than to what LM Studio is.

### What LAS Gains

| Feature | Build In-House | Via AnythingLLM |
|---------|---------------|-----------------|
| Chat UI with threading | Months | Free |
| Workspace isolation (sandboxes) | Weeks | Free |
| Document ingestion + RAG | Months | Free |
| Multi-user with RBAC | Weeks | Free |
| Browser extension (clip-to-workspace) | N/A | Free |
| MCP tool calling in agent flows | Already have | Complementary |
| Conversation branching/regeneration | Not planned | Free |

### What AnythingLLM Gets From LAS

1. **Expert specialist routing** — LAS's Router directs queries to the right specialist
2. **Structured agentic workflows** — graph-based state management, not just imperative tool calls
3. **Self-critique** — ExitInterview verifies task completion before returning results
4. **Multi-model orchestration** — LAS can use different models for different specialists
5. **Completion signaling** — structured COMPLETED/PARTIAL/BLOCKED/ERROR status

---

## Proposed Integration: LAS as OpenAI-Compatible Backend

### Option Analysis

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| A. LAS as MCP server | AnythingLLM calls LAS tools via MCP | Clean separation, tool-level granularity | Requires `@agent` invocation, not default chat |
| **B. LAS as inference backend** | LAS exposes `/v1/chat/completions` | Drop-in, default chat path, any OpenAI client works | Must translate between OpenAI format and LAS internals |
| C. Side-by-side | Both use LM Studio independently | No integration work | No integration benefit |
| D. LAS masquerades as AnythingLLM | LAS fakes AnythingLLM's REST API | Full feature emulation | Impractical — workspace/vector DB state is complex |

**Recommended: Option B** — LAS exposes an OpenAI-compatible `/v1/chat/completions` endpoint. AnythingLLM (and any other client) connects to it as "Generic OpenAI."

> **Update (2026-03-06):** AnythingLLM's **Generic OpenAI** provider is the correct integration target — not the LM Studio provider. Generic OpenAI takes a freeform model name string and base URL without trying to enumerate loaded GGUF models via `/v1/models`. This means LAS can use the model name field as a **task profile selector** (e.g., `las-research`, `las-bugtriage`) without faking a model list. The LM Studio provider would fight us on model discovery.
>
> **Custom Agent Skills** (Option A complement): AnythingLLM supports `handler.js` + `plugin.json` custom skills that can call external APIs. A "delegate to LAS" skill could `POST` to the proxy for complex tasks while keeping simple queries on AnythingLLM's own LLM. Options A and B are complementary, not exclusive.
>
> **CUA integration**: AnythingLLM now supports Computer Use Agent workflows. Worth monitoring but premature to integrate — surf-mcp already covers browser automation, and adding a second browser path creates dual-source complexity.

### API Translation Layer

```
AnythingLLM                          LAS
─────────────────────────────────────────────
POST /v1/chat/completions    →    Translate to InvokeRequest
  messages: [...]                   input_prompt: last user message
  model: "las-default"              (route through specialist graph)
  stream: true
                              ←    Stream specialist activity as SSE
  choices[0].delta.content          final_user_response from artifacts
  usage.total_tokens                routing_history, latency metadata
```

### What Gets Exposed

| OpenAI Field | LAS Source |
|-------------|-----------|
| `choices[0].message.content` | `artifacts.final_user_response` |
| `model` | Specialist routing path (e.g., `las/triage→sa→pd→ei`) |
| `usage.prompt_tokens` | Aggregate across specialist calls |
| `usage.completion_tokens` | Aggregate across specialist calls |
| `finish_reason` | `completion_signal.status` mapped to `stop`/`length` |

### Extended Metadata (Optional)

For clients that understand it, LAS can include non-standard fields:

```json
{
  "choices": [{"message": {"content": "..."}}],
  "las_metadata": {
    "routing_history": ["triage_architect", "systems_architect", "project_director"],
    "completion_signal": {"status": "COMPLETED", "summary": "..."},
    "archive_id": "run_20260303_022959_f03fed24",
    "specialist_count": 7,
    "total_latency_ms": 45000
  }
}
```

AnythingLLM ignores unknown fields. Clients that understand LAS can read them.

---

## Implementation Sketch

### Phase 1: Minimal Viable Endpoint

New file: `app/src/api_openai.py`

1. `POST /v1/chat/completions` — accepts OpenAI message format, invokes LAS graph, returns completion
2. `GET /v1/models` — returns available LAS configurations as "models" (e.g., `las-default`, `las-research`, `las-categorize`)
3. SSE streaming: emit `data: {"choices": [{"delta": {"content": "..."}}]}` chunks as specialists complete

### Phase 2: Model Manifest as Profile Registry

Each "model" in the `/v1/models` response maps to a `user_settings.yaml` profile:

| Model ID | LAS Behavior | Settings Profile |
|----------|-------------|-----------------|
| `las-default` | Full specialist routing (triage → SA → PD → EI) | `default` |
| `las-direct` | Skip routing, send directly to PD with default tools | `direct` |
| `las-research` | Route to TextAnalysis specialist with semantic chunker | `research` |
| `las-bugtriage` | PD with filesystem-mcp (`.graphs/`), terminal-mcp (`gh`) | `bugtriage` |
| `las-passthrough` | Forward to LM Studio directly (LAS as transparent proxy) | `passthrough` |

The `/v1/models` manifest includes metadata for discoverability:

```json
{
  "object": "list",
  "data": [
    {
      "id": "las-research",
      "object": "model",
      "owned_by": "las",
      "metadata": {
        "settings_profile": "research",
        "specialists": ["PD"],
        "mcp_servers": ["surf", "semantic-chunker"],
        "default_model": "qwen3.5-9b"
      }
    }
  ]
}
```

AnythingLLM ignores `metadata`; LAS tooling (prompt-prix eval, trace analysis) can query `/v1/models` to discover profiles. The model name in each trace is the profile key — solving run-to-settings provenance.

New profile = new YAML file + proxy restart (or hot-reload) → appears in manifest.

### Phase 3: Streaming Specialist Activity

During graph execution, emit intermediate SSE events so the UI shows progress:

```
data: {"choices":[{"delta":{"content":"[triage] Analyzing request...\n"}}]}
data: {"choices":[{"delta":{"content":"[systems_architect] Planning approach...\n"}}]}
data: {"choices":[{"delta":{"content":"[project_director] Executing (3/7 tools)...\n"}}]}
data: {"choices":[{"delta":{"content":"\n---\nAll 13 files categorized into 6 folders.\n"}}]}
data: [DONE]
```

---

## AnythingLLM-Specific Integration Notes

### Workspace Model

Each AnythingLLM workspace can point to a different LAS "model":

- **Analysis workspace** → `las-research` (semantic analysis via TextAnalysis specialist)
- **Project workspace** → `las-default` (full specialist routing for agentic tasks)
- **Quick chat workspace** → `las-passthrough` (transparent proxy to LM Studio)

### RAG Interaction

AnythingLLM's RAG pipeline runs **before** the LLM call. Retrieved document chunks are prepended to the messages array. LAS receives them as part of the user message context — no special handling needed.

### Agent Flows

AnythingLLM's `@agent` directive activates its own ReAct loop. If LAS is the backend, this creates nested orchestration (AnythingLLM's agent → LAS's specialist graph → LAS's PD ReAct loop). This may be desirable for complex workflows or problematic for latency. Phase 1 should focus on direct chat, not agent-in-agent.

### MCP Complementarity

AnythingLLM supports MCP tools (v1.8.0+). LAS's existing MCP servers (filesystem, terminal, semantic-chunker, prompt-prix) could be registered in AnythingLLM as well. However, if LAS is the inference backend, tool routing should go through LAS's specialist graph rather than AnythingLLM's agent, to avoid competing orchestration.

---

## Networking (Docker)

```
AnythingLLM (port 3001)
    │
    ├── connects to LAS as "LM Studio" → http://host.docker.internal:8000
    │   (OpenAI-compatible /v1/chat/completions)
    │
    ├── connects to actual LM Studio → http://host.docker.internal:1234
    │   (for las-passthrough model, or embedding)
    │
    └── vector DB (built-in or external)
```

On Linux: `--add-host=host.docker.internal:host-gateway` for the AnythingLLM container.

---

## Decision Criteria

**Proceed if:**
- The `/v1/chat/completions` translation layer can be built in < 1 day
- AnythingLLM correctly discovers models via `/v1/models`
- Streaming SSE works through AnythingLLM's proxy without corruption

**Defer if:**
- AnythingLLM requires non-standard handshake or capabilities negotiation
- The workspace/RAG layer interferes with LAS's own context management
- Agent-in-agent nesting creates unacceptable latency

---

## Comparison: AnythingLLM vs LM Studio vs Ollama

| Feature | Ollama | LM Studio | AnythingLLM |
|---------|--------|-----------|-------------|
| **Purpose** | Inference engine | Desktop chat + inference | Orchestration framework |
| **UI** | CLI only | Desktop app | Desktop + Docker + Web |
| **Multi-user** | No | No | Yes (Docker) |
| **RAG** | No | No | Yes |
| **Agent workflows** | No | No | Yes (Flows + ReAct) |
| **MCP support** | No | No | Yes (v1.8.0+) |
| **LLM backends** | Ollama models only | Local models only | 15+ providers |
| **API** | Minimal | OpenAI-compatible | Full REST API (v1) |
| **Workspace isolation** | No | No | Yes |
| **Document ingestion** | No | No | Yes (PDF, DOCX, code, audio, web) |
| **Browser extension** | No | No | Yes (clip-to-workspace) |

---

## Risks

1. **Competing orchestration**: AnythingLLM has its own agent/RAG layer. If both AnythingLLM and LAS try to orchestrate, results may be unpredictable. Mitigation: clear model IDs that signal which layer handles orchestration.

2. **Streaming fidelity**: SSE through AnythingLLM's proxy may buffer or corrupt streaming events. Needs empirical testing.

3. **Version coupling**: AnythingLLM updates may change how it communicates with backends. OpenAI-compatible API is stable, but edge cases exist.

4. **Latency**: LAS specialist routing adds overhead vs direct LM Studio inference. The `las-passthrough` model provides an escape hatch.

---

## References

- [AnythingLLM Official Documentation](https://docs.anythingllm.com/)
- [AnythingLLM GitHub — mintplex-labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm)
- [AnythingLLM MCP Compatibility](https://docs.anythingllm.com/mcp-compatibility/overview)
- [AnythingLLM API Access](https://docs.useanything.com/features/api)
- [AnythingLLM Agent Flows](https://docs.anythingllm.com/agent-flows/overview)
- [AnythingLLM Custom Agent Skills](https://docs.anythingllm.com/agent/custom/developer-guide)
- [AnythingLLM LM Studio Configuration](https://docs.useanything.com/setup/llm-configuration/local/lmstudio)
- [AnythingLLM Docker Installation](https://docs.anythingllm.com/installation-docker/local-docker)
- LAS ADR-CORE-068: Inference-As-Service Pool Extraction
- LAS ADR-CORE-052: Migration to Adapter-Registry Pattern
- LM Studio bugs: #1592, #1593, #1589 (motivation for decoupling from LM Studio UI)
- [AnythingLLM Generic OpenAI Provider](https://docs.anythingllm.com/setup/llm-configuration/cloud/openai-generic) — target integration provider
- [handler.js reference](https://docs.anythingllm.com/agent/custom/handler-js) — custom agent skill entry point
- [plugin.json reference](https://docs.anythingllm.com/agent/custom/plugin-json) — custom agent skill manifest
- llama.cpp autoparser (ggml-org/llama.cpp#13548) — upstream fix for LM Studio parser bugs, reduces motivation for `las-passthrough`

---

## Implementation Record

**Date:** 2026-04-03

### What Was Built

**Phase 1 (OpenAI endpoint) — COMPLETE:**
- `POST /v1/chat/completions` — streaming and sync, spec-compliant with no vendor extensions
- `GET /v1/models` — returns `las-default` and `las-simple` as routing profiles
- `OpenAiTranslator` consumes raw LangGraph events, produces `ChatCompletionChunk` SSE
- `OpenAiRequestAdapter` translates OpenAI message format to `WorkflowRunner` kwargs
- Interrupt/clarification degrades gracefully (questions returned as regular content)
- 47 unit tests covering schema, request translation, response formatting, and streaming

**Phase 2 (model profiles) — PARTIAL:**
- Model field works as routing profile selector (`las-default`, `las-simple`)
- Full profile registry from `user_settings.yaml` deferred — two hardcoded profiles suffice for current use

**Phase 3 (streaming activity) — SUPERSEDED by ADR-UI-003:**
- Chat stream is silent during execution (by design). Observability data travels on its own channel (`/v1/runs/{run_id}/events`). The `las_metadata` approach was dropped per ADR-UI-003.

### What Changed From Proposal

- **No `las_metadata` on chunks** — ADR-UI-003 separated observability from the chat stream entirely
- **No `api_openai.py`** — endpoints live in `api.py` alongside other chat endpoints, using `interface/openai_*.py` modules for translation
- **Generic OpenAI confirmed** — the freeform model name field works as predicted
- **AnythingLLM empirical validation still pending** — the endpoint works with curl and OpenAI SDK; AnythingLLM-specific testing (RAG interaction, workspace model, streaming fidelity) remains to be done with lived experience

### Files

| File | Role |
|------|------|
| `app/src/interface/openai_schema.py` | Pydantic models for OpenAI request/response |
| `app/src/interface/openai_request_adapter.py` | Translates OpenAI messages → WorkflowRunner kwargs |
| `app/src/interface/openai_response_formatter.py` | Formats final state as sync ChatCompletion |
| `app/src/interface/openai_translator.py` | Raw events → ChatCompletionChunk SSE stream |
| `app/src/api.py` | `/v1/chat/completions` and `/v1/models` endpoints |
| `app/tests/unit/test_openai_*.py` | 47 unit tests |
