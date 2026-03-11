# ADR: CORE-CHAT-002 - Tiered Chat Implementation Decisions

**Status:** Completed

**Date:** 2025-11-05

**Prerequisites:** CORE-CHAT-001

---

## Decision Summary

This document consolidates the final decisions for CORE-CHAT-002.1 (Graceful Degradation Strategy) and CORE-CHAT-002.2 (Virtual Coordinator Pattern) based on architectural review and implementation constraints.

---

## PART 1: Graceful Degradation Strategy (002.1)

### **Decision: Modified Option B - Graceful Degradation with Consistent Format**

**Core Principle:** Always use TieredSynthesizerSpecialist when tiered chat is enabled, even with partial responses.

### **Failure Handling Behavior**

When tiered chat is enabled and a progenitor fails:

1. **Both responses present** → Standard tiered formatting with both perspectives
2. **Only alpha_response present** → TieredSynthesizer formats single perspective with explanatory note
3. **Only bravo_response present** → TieredSynthesizer formats single perspective with explanatory note  
4. **Neither present** → Raise error and route to END with error_report (complete system failure)

**Key Difference from Original ADR:** Do NOT fall back to single ChatSpecialist on partial failure. Always maintain tiered output format for consistency.

### **User-Facing Configuration**

**Requirement:** Tiered chat must be exposed as a boolean in both API and UI.

**API Implementation:**
```python
# In API request body
{
    "prompt": "user query here",
    "tiered_chat_enabled": true  # Optional, defaults to user preference
}
```

**UI Implementation:**
- User preferences/settings toggle: "Enable Multi-Perspective Chat"
- Per-request override available in advanced options
- Persists to user profile for default behavior

**Config Hierarchy:**
1. Per-request API parameter (highest priority)
2. User UI preference setting
3. System default from config.yaml (lowest priority)

### **Response Metadata**

All responses include `response_mode` in metadata:

- `"tiered_full"` - Both progenitors responded successfully
- `"tiered_alpha_only"` - Only ProgenitorAlpha responded
- `"tiered_bravo_only"` - Only ProgenitorBravo responded
- `"single_fallback"` - Tiered chat disabled, used single ChatSpecialist
- `"error"` - Complete failure (neither progenitor responded)

### **Configuration Options**

**In config.yaml:**
```yaml
chat_specialist:
  tiered_chat:
    enabled_by_default: false  # System-wide default
    require_all_progenitors: false  # If true, fail fast when partial
    timeout_seconds: 30  # Per-progenitor timeout
```

**In user_settings.yaml:**
```yaml
llm_providers:
  gemini_pro:
    type: "gemini"
    api_identifier: "gemini-2.5-pro"
  lmstudio_specialist:
    type: "lmstudio"
    api_identifier: "gemma-3-27b-it-abliterated@q5_k_m"
  gemini_flash:
    type: "gemini"
    api_identifier: "gemini-2.5-flash"

specialist_model_bindings:
  progenitor_alpha_specialist: "gemini_pro"
  progenitor_bravo_specialist: "lmstudio_specialist"
  tiered_synthesizer_specialist: "gemini_flash"
```

### **TieredSynthesizerSpecialist Implementation Requirements**

The TieredSynthesizerSpecialist must:

1. **Check for responses in GraphState:**
   - `artifacts.alpha_response` (from ProgenitorAlpha)
   - `artifacts.bravo_response` (from ProgenitorBravo)

2. **Format output based on what's available:**
   ```python
   if alpha_response and bravo_response:
       # Standard tiered format
       output = f"""## Perspective 1 (Alpha)
   {alpha_response}
   
   ## Perspective 2 (Bravo)
   {bravo_response}"""
       response_mode = "tiered_full"
   
   elif alpha_response:
       # Graceful degradation - single perspective
       output = f"""## Response (Single Perspective)
   {alpha_response}
   
   *Note: Second perspective unavailable due to system error.*"""
       response_mode = "tiered_alpha_only"
   
   elif bravo_response:
       # Graceful degradation - single perspective
       output = f"""## Response (Single Perspective)
   {bravo_response}
   
   *Note: Primary perspective unavailable due to system error.*"""
       response_mode = "tiered_bravo_only"
   
   else:
       # Complete failure
       raise ValueError("No progenitor responses available")
   ```

3. **Write to state:**
   ```python
   return {
       "messages": [ai_message],
       "scratchpad": {"user_response_snippets": [output]},
       "task_is_complete": True,
       "artifacts": {"response_mode": response_mode}
   }
   ```

### **Logging and Observability**

- Log at WARNING level when operating in degraded mode
- Include failure reasons in structured logs
- LangSmith traces show which progenitors executed successfully
- Archive Report includes response_mode for post-hoc analysis

### **Rationale**

- **User experience:** Degraded output is better than complete failure
- **Format consistency:** Always using TieredSynthesizer ensures predictable output structure
- **Transparency:** Response metadata clearly indicates degraded mode
- **Debuggability:** Logs and traces provide failure diagnostics
- **User control:** Boolean toggle makes feature discoverable and controllable

---

## PART 2: Virtual Coordinator Pattern (002.2)

### **Decision: Option A - Virtual Coordinator with Orchestrator-Level Interception**

**Core Principle:** Router selects "chat_specialist" (abstract capability), Orchestrator translates to concrete implementation (parallel progenitors or single specialist).

### **Semantic Model**

- **Router's perspective:** "The user needs chat capability" → routes to `"chat_specialist"`
- **Orchestrator's perspective:** "How do we provide chat?" → fan-out to progenitors if tiered enabled
- **Separation of concerns:** Router decides WHAT, Orchestrator decides HOW

### **Graph Structure**

**When tiered chat is ENABLED:**
- `chat_specialist` appears in config.yaml
- `chat_specialist` appears in router's tool schema (router can choose it)
- `chat_specialist` is NOT added as a graph node
- `progenitor_alpha_specialist`, `progenitor_bravo_specialist`, `tiered_synthesizer_specialist` are added as nodes
- Progenitors are excluded from router's tool schema (internal to subgraph)

**When tiered chat is DISABLED:**
- `chat_specialist` appears in config.yaml
- `chat_specialist` appears in router's tool schema
- `chat_specialist` IS added as a graph node
- Progenitor specialists are not instantiated

### **Routing Implementation**

**In GraphOrchestrator.route_to_next_specialist():**
```python
def route_to_next_specialist(self, state: GraphState) -> Union[str, List[str]]:
    """
    Route to next specialist based on router's decision.
    Intercepts 'chat_specialist' routing to implement tiered chat pattern.
    """
    next_specialist = state.get("routing_decision")
    
    # Virtual Coordinator Pattern: Intercept chat_specialist routing
    if next_specialist == "chat_specialist":
        tiered_chat_enabled = self._is_tiered_chat_enabled(state)
        
        if tiered_chat_enabled:
            logger.info(
                "Chat routing detected - fanning out to parallel progenitors",
                extra={"routing_mode": "tiered_parallel"}
            )
            return ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]
        else:
            logger.info(
                "Chat routing detected - using single specialist",
                extra={"routing_mode": "single_chat"}
            )
            return "chat_specialist"
    
    # Standard routing for all other specialists
    return next_specialist

def _is_tiered_chat_enabled(self, state: GraphState) -> bool:
    """
    Determine if tiered chat should be used for this request.
    Priority: API request > user preference > config default
    """
    # Check per-request override
    if "tiered_chat_enabled" in state.get("user_context", {}):
        return state["user_context"]["tiered_chat_enabled"]
    
    # Check user preference (from user profile)
    if "user_preferences" in state.get("user_context", {}):
        prefs = state["user_context"]["user_preferences"]
        if "tiered_chat_enabled" in prefs:
            return prefs["tiered_chat_enabled"]
    
    # Fall back to config default
    return self.config.get("chat_specialist", {}).get("tiered_chat", {}).get("enabled_by_default", False)
```

**In GraphBuilder._wire_hub_and_spoke_edges():**
```python
def _wire_hub_and_spoke_edges(self):
    """Wire conditional edges from router to specialists."""
    
    # Build destination map
    destinations = {}
    for name in self.specialists:
        if name == self.router_name:
            continue
        
        # Include chat_specialist in destinations even if not a node
        # (router needs to be able to choose it)
        destinations[name] = name
    
    # Add conditional edge from router
    self.workflow.add_conditional_edges(
        self.router_name,
        self.orchestrator.route_to_next_specialist,
        destinations
    )
```

**In GraphBuilder.add_specialists():**
```python
def add_specialists(self):
    """Add specialist nodes to graph."""
    
    tiered_chat_config = self.config.get("chat_specialist", {}).get("tiered_chat", {})
    has_tiered_chat = (
        tiered_chat_config.get("enabled_by_default", False) or
        self._has_tiered_chat_specialists()
    )
    
    for name, specialist in self.specialists.items():
        if name == self.router_name:
            continue
        
        # Skip chat_specialist node if tiered chat is enabled
        if name == "chat_specialist" and has_tiered_chat:
            logger.info(
                f"Skipping {name} node - tiered chat subgraph enabled",
                extra={"subgraph": "tiered_chat"}
            )
            continue
        
        # Add specialist as node
        self.workflow.add_node(name, specialist)

def _has_tiered_chat_specialists(self) -> bool:
    """Check if all tiered chat specialists are configured."""
    required = [
        "progenitor_alpha_specialist",
        "progenitor_bravo_specialist", 
        "tiered_synthesizer_specialist"
    ]
    return all(s in self.specialists for s in required)
```

### **Configuration**

**Router Configuration (config.yaml):**
```yaml
router_specialist:
  type: "llm"
  prompt_file: "router_prompt.md"
  description: "Routes user requests to appropriate specialists"
  excluded_from_routing:
    - router_specialist
    - progenitor_alpha_specialist  # Internal to tiered chat subgraph
    - progenitor_bravo_specialist  # Internal to tiered chat subgraph
    - tiered_synthesizer_specialist  # Internal to tiered chat subgraph

chat_specialist:
  type: "llm"
  prompt_file: "chat_prompt.md"
  description: "General-purpose conversational specialist for Q&A and chat"
  tiered_chat:
    enabled_by_default: false
```

### **Observability**

**Logging:**
- INFO level when interception occurs: "Chat routing detected - fanning out to parallel progenitors"
- Include routing_mode in structured logs: "tiered_parallel" vs "single_chat"

**LangSmith Traces:**
- routing_history will show: `["router_specialist", "progenitor_alpha_specialist", "progenitor_bravo_specialist", "tiered_synthesizer_specialist"]`
- Parallel execution visible in trace timeline
- Message names indicate which specialists ran

**Archive Report:**
- Include response_mode: "tiered_full", "tiered_alpha_only", etc.
- routing_history shows actual execution path
- Include tiered_chat_enabled flag in request metadata

**Documentation:**
- DEVELOPERS_GUIDE.md explains Virtual Coordinator pattern
- ASCII diagram showing router decision → orchestrator interception → parallel execution

### **Backward Compatibility**

When tiered chat is disabled:
- Router can still choose "chat_specialist"
- Orchestrator routes directly to single ChatSpecialist node
- No progenitor specialists instantiated
- Standard single-perspective response

### **Future Migration Paths**

If Virtual Coordinator pattern proves problematic:

**Option 1: Intent-Based Routing**
- Router distinguishes "simple_chat" vs "complex_chat"
- simple_chat → single specialist
- complex_chat → tiered subgraph

**Option 2: LangGraph Nested Subgraph**
```python
chat_subgraph = StateGraph(GraphState)
chat_subgraph.add_node("alpha", ProgenitorAlpha)
chat_subgraph.add_node("bravo", ProgenitorBravo)
chat_subgraph.add_node("synthesizer", TieredSynthesizer)
workflow.add_node("chat_specialist", chat_subgraph.compile())
```

**Option 3: Dynamic Routing Function**
```python
def dynamic_chat_router(state):
    if should_use_tiered(state):
        return ["alpha", "bravo"]
    return "chat_specialist"
```

### **Rationale**

- **Separation of concerns:** Router decides capability needs, Orchestrator decides implementation
- **Backward compatibility:** Single specialist works seamlessly when tiered disabled
- **Progressive enhancement:** Multi-perspective is internal improvement, router unaware
- **User control:** Boolean toggle makes architectural choice discoverable
- **Flexibility:** Model bindings in user_settings.yaml enable cost/quality optimization
- **Precedent:** EndSpecialist already uses hybrid coordinator pattern

---

## Model-Agnostic Architecture

### **Key Principle**

The entire tiered chat architecture (and future Diplomatic Process) can be implemented with ANY model configuration. Concrete model bindings are runtime configuration, not architectural constraints.

### **Configuration Examples**

**Development (zero API cost):**
```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "lmstudio_specialist"
  progenitor_bravo_specialist: "lmstudio_router"
  tiered_synthesizer_specialist: "lmstudio_router"
```

**Hybrid (mixed cost/quality):**
```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "gemini_pro"
  progenitor_bravo_specialist: "lmstudio_specialist"
  tiered_synthesizer_specialist: "gemini_flash"
```

**Production (when PAYG justified):**
```yaml
specialist_model_bindings:
  progenitor_alpha_specialist: "gemini_pro"
  progenitor_bravo_specialist: "claude_sonnet"
  tiered_synthesizer_specialist: "gemini_flash"
```

### **Strategic Advantage**

- Build complete infrastructure now
- Validate architectural patterns without financial risk
- Demonstrate value before committing to API costs
- Upgrade models by changing one line in config
- A/B test model combinations without code changes

---

## Implementation Checklist

### GraphBuilder Modifications
- [ ] Implement tiered chat detection in `add_specialists()`
- [ ] Skip chat_specialist node when tiered enabled
- [ ] Include chat_specialist in router tool schema regardless
- [ ] Exclude progenitors from router tool schema
- [ ] Add join edges: progenitors → tiered_synthesizer

### GraphOrchestrator Modifications
- [ ] Implement `route_to_next_specialist()` interception
- [ ] Add `_is_tiered_chat_enabled()` helper method
- [ ] Add structured logging for routing decisions
- [ ] Handle priority: API request > user pref > config default

### TieredSynthesizerSpecialist Implementation
- [ ] Check for alpha_response and bravo_response in GraphState
- [ ] Format output based on available responses
- [ ] Add explanatory notes for degraded modes
- [ ] Write to scratchpad.user_response_snippets
- [ ] Return task_is_complete: True
- [ ] Include response_mode in artifacts

### Configuration Files
- [ ] Add tiered_chat section to config.yaml
- [ ] Add progenitor bindings to user_settings.yaml example
- [ ] Document configuration hierarchy in README

### API Modifications
- [ ] Add tiered_chat_enabled to request schema
- [ ] Add response_mode to response schema
- [ ] Document API parameter in OpenAPI spec

### UI Modifications
- [ ] Add "Enable Multi-Perspective Chat" toggle to settings
- [ ] Persist preference to user profile
- [ ] Show response_mode indicator in chat UI
- [ ] Add explanatory tooltip for feature

### Observability
- [ ] Add structured logging with routing_mode
- [ ] Ensure LangSmith traces show parallel execution
- [ ] Include response_mode in Archive Report
- [ ] Add health check endpoint for subgraph status

### Documentation
- [ ] Update DEVELOPERS_GUIDE.md with Virtual Coordinator pattern
- [ ] Add ASCII diagram of routing flow
- [ ] Document model binding examples
- [ ] Add troubleshooting section for degraded modes

### Testing
- [ ] Unit tests for graceful degradation scenarios
- [ ] Integration tests for virtual coordinator routing
- [ ] Tests for configuration priority hierarchy
- [ ] Tests for all response_mode states
- [ ] Load tests with progenitor failures

---

## Success Criteria

- [ ] Router can choose "chat_specialist" via normal tool calling
- [ ] When tiered enabled, parallel execution occurs automatically
- [ ] When tiered disabled, single ChatSpecialist works as before
- [ ] Partial progenitor failures result in degraded but functional output
- [ ] Response metadata clearly indicates operational mode
- [ ] LangSmith traces show actual execution path
- [ ] No graph compilation errors
- [ ] API boolean toggle controls feature per-request
- [ ] UI preference persists across sessions
- [ ] Model bindings can be changed without code modifications

---

## Related ADRs

- **CORE-CHAT-001:** Foundational ChatSpecialist (prerequisite)
- **CORE-CHAT-002:** Tiered Chat Subgraph (parent ADR)
- **CORE-CHAT-003:** Diplomatic Chat Subgraph (will use same patterns)

---

**Approved By:** [Project Lead]  
**Implementation Target:** Phase 1 - Pre-Production
