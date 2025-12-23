# LAS Happy Paths

Core user journeys that demonstrate LAS working as designed. Each path shows the **expected flow** with potential failover noted.

---

## 1. Conversational Query (Tiered Chat)

**Trigger:** User asks a question or makes a conversational request.

```
User: "What are the key differences between Python and JavaScript?"
    │
    ▼
┌─────────────────┐
│ Triage Architect│  Analyzes: No context needed, ready to route
└────────┬────────┘
         │ recommended_specialists: ["chat_specialist"]
         ▼
┌─────────────────┐
│     Router      │  Routes to tiered_chat_entrypoint
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐  ┌───────┐
│ Alpha │  │ Bravo │  Parallel progenitors (different models)
│Gemini │  │Claude │
└───┬───┘  └───┬───┘
    │          │
    └────┬─────┘
         ▼
┌─────────────────┐
│TieredSynthesizer│  Combines perspectives, formats response
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  End Specialist │  Archives, returns to user
└─────────────────┘
```

**Failover:** If one progenitor fails, synthesizer uses single response with degradation notice.

---

## 2. File Operations

**Trigger:** User requests file read/write/list within workspace.

```
User: "Read the contents of config.yaml"
    │
    ▼
┌─────────────────┐
│ Triage Architect│  Detects: File operation request
└────────┬────────┘
         │ context_plan: [READ_FILE: "config.yaml"]
         ▼
┌─────────────────┐
│   Facilitator   │  Executes context plan
│                 │  MCP call → file_specialist.read_file()
└────────┬────────┘
         │ gathered_context: {config.yaml: "...content..."}
         ▼
┌─────────────────┐
│     Router      │  Context available, routes to chat
└────────┬────────┘
         ▼
┌─────────────────┐
│  Chat/Response  │  Presents file content to user
└─────────────────┘
```

**Failover:** File not found → clear error message with path suggestions.

---

## 3. Web Browser Automation

**Trigger:** User requests web interaction (navigate, click, fill form).

```
User: "Go to github.com and click on the Sign In button"
    │
    ▼
┌─────────────────┐
│ Triage Architect│  Detects: Web navigation request
└────────┬────────┘
         │ recommended_specialists: ["navigator_browser_specialist"]
         ▼
┌─────────────────┐
│     Router      │  Routes to browser specialist
└────────┬────────┘
         ▼
┌─────────────────────────┐
│NavigatorBrowserSpecialist│
│  1. Create session       │
│  2. goto("github.com")   │──► surf-mcp container
│  3. click("Sign In")     │    └── Fara visual grounding
│  4. screenshot()         │        └── LMStudio vision model
└────────┬────────────────┘
         │ artifacts: {screenshot: "...", session_id: "..."}
         ▼
┌─────────────────┐
│  End Specialist │  Returns screenshot, preserves session
└─────────────────┘
```

**Failover:** Element not found → Fara re-attempts with alternate descriptions.

---

## 4. HTML Generation with Critique

**Trigger:** User requests UI/HTML creation.

```
User: "Create a landing page for a coffee shop"
    │
    ▼
┌─────────────────┐
│ Triage Architect│  Detects: UI generation request
└────────┬────────┘
         │ recommended_specialists: ["web_builder"]
         ▼
┌─────────────────┐
│  Web Builder    │  Generates HTML artifact
└────────┬────────┘
         │ artifacts: {html_document: "..."}
         │ recommended_specialists: ["critic_specialist"]
         ▼
┌─────────────────┐
│    Critic       │  Reviews HTML against requirements
└────────┬────────┘
         │ scratchpad: {critique_decision: "ACCEPT" | "REVISE"}
         │
    ┌────┴────┐
    │ REVISE  │ ACCEPT
    ▼         ▼
┌─────────┐  ┌─────────────────┐
│Web Build│  │  End Specialist │  Returns accepted HTML
│ (retry) │  └─────────────────┘
└─────────┘
```

**Failover:** Max 3 revision cycles, then accepts with disclaimer.

---

## 5. Deep Research

**Trigger:** User requests investigation requiring multiple sources.

```
User: "Research the current state of quantum computing in 2025"
    │
    ▼
┌─────────────────┐
│ Triage Architect│  Detects: Research request, complex
└────────┬────────┘
         │ recommended_specialists: ["research_orchestrator"]
         ▼
┌──────────────────────┐
│ Research Orchestrator │  Controller (ReActMixin)
│  ┌─────────────────┐ │
│  │ Loop until done │ │
│  │  1. Decide next │ │
│  │  2. Search/Browse│ │
│  │  3. Judge relevance│
│  │  4. Update KB   │ │
│  └─────────────────┘ │
└────────┬─────────────┘
         │ Calls MCP services:
         │   - web_specialist (search)
         │   - browse_specialist (fetch)
         │   - inference_service (judge)
         ▼
┌─────────────────┐
│   Synthesizer   │  Compiles research into report
└────────┬────────┘
         │ artifacts: {research_report: "..."}
         ▼
┌─────────────────┐
│  End Specialist │  Returns comprehensive report
└─────────────────┘
```

**Failover:** Search failures → try alternate queries; max iterations → synthesize partial results.

---

## 6. Context Engineering (Pre-flight)

**Trigger:** Any request that may need context before routing.

```
User: "Summarize the README file"
    │
    ▼
┌─────────────────────────────┐
│      Triage Architect       │
│  Analyzes request:          │
│  - Needs file? YES          │
│  - Which file? README.md    │
│  - Ready to route? NO       │
└────────┬────────────────────┘
         │ context_plan: {
         │   actions: [READ_FILE("README.md")],
         │   reasoning: "Need file content for summarization"
         │ }
         ▼
┌─────────────────────────────┐
│        Facilitator          │
│  Executes plan:             │
│  1. MCP call: file_specialist.read_file("README.md")
│  2. Store in gathered_context
└────────┬────────────────────┘
         │ gathered_context: {README.md: "...content..."}
         ▼
┌─────────────────────────────┐
│          Router             │
│  Now has context, routes to │
│  summarizer or chat         │
└─────────────────────────────┘
```

**Failover:** Context gathering fails → route anyway with error context.

---

## Pattern Summary

| Pattern | Entry | Core Flow | Exit |
|---------|-------|-----------|------|
| **Chat** | Triage → Router | Alpha ∥ Bravo → Synthesize | End |
| **File Ops** | Triage → Facilitate | MCP → file_specialist | End |
| **Browser** | Triage → Router | NavigatorBrowser → surf-mcp | End |
| **HTML Gen** | Triage → Router | WebBuilder ↔ Critic loop | End |
| **Research** | Triage → Router | Orchestrator ReAct loop | End |
| **Context** | Triage | Facilitate → gather | Router |

---

## Invariants (Always True)

1. **Entry**: All requests start at Triage Architect
2. **Exit**: All successful requests end at End Specialist (archival)
3. **State**: GraphState is never mutated directly by specialists
4. **Safety**: NodeExecutor wraps all specialist execution
5. **Failover**: Circuit breaker triggers after invariant violations

---

## Not Covered (Known Gaps)

- **Distillation subgraph**: Training data generation (niche use case)
- **Convening of the Tribes**: Multi-agent orchestration (advanced)
- **Open Interpreter**: Code execution (security-sensitive)
