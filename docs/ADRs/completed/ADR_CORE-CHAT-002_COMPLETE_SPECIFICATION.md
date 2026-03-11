# ADR: CORE-CHAT-002 - Tiered Chat Implementation (Complete Specification)

**Status:** Completed

**Date:** 2025-11-05

**Prerequisites:** CORE-CHAT-001

---

## Decision Summary

This document consolidates all decisions for CORE-CHAT-002, including:
- CORE-CHAT-002.1: Graceful Degradation Strategy
- CORE-CHAT-002.2: Virtual Coordinator Pattern
- Multi-Turn Context Management Strategy

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

---

## PART 3: Multi-Turn Context Management Strategy

### **Decision: The Accurate History Strategy (Transparent Tiered History)**

**Core Principle:** Maintain a single, unified `GraphState.messages` list that accurately reflects what the user saw in previous turns.

**For CORE-CHAT-002:** Implement **Option B - Transparent Tiered History**. The history contains the full tiered response showing both perspectives.

### **Rationale**

**Source:** Deep Think Architectural Analysis (2025-11-05)

1. **Coherence is Mandatory:** Conversational coherence is a prerequisite for functional dialogue. Isolated thread models fail catastrophically when users cross-reference perspectives.

2. **Implementation Simplicity:** Utilizes existing GraphState structure and LangGraph primitives (`add_messages`), aligning with LAS architectural philosophy.

3. **Scalability:** Extends cleanly to CORE-CHAT-003 (Diplomatic Process), where the Arbiter requires unified history.

4. **Token Efficiency:** Linear growth of ~900 tokens/turn is sustainable within modern 128k context windows.

### **The Cross-Referencing Problem**

**Scenario demonstrating why isolated threads fail:**

```
Turn 1:
User: "Explain quantum entanglement"
Alpha: "It's like two coins that always land opposite."
Bravo: "It's a complex mathematical correlation..."

Turn 2:
User: "Can you expand on that coin analogy?"
```

**With Isolated Threads (Rejected):**
- Bravo sees its mathematical view and the request about "coin analogy"
- Bravo never mentioned coins → conversation breaks down

**With Transparent Tiered History (Approved):**
- Bravo sees full Turn 1 exchange including Alpha's analogy
- Bravo can intelligently engage, criticize, or bridge perspectives
- Conversation remains coherent

### **State Management Pattern (Critical Implementation Detail)**

The implementation relies on temporary storage during parallel execution and updating messages only at the join node.

#### **Pattern Overview**

1. **Progenitor Execution (Parallel):**
   - Progenitors consume current `GraphState.messages` for context
   - Write responses to temporary storage: `artifacts.alpha_response`, `artifacts.bravo_response`
   - **MUST NOT** append directly to `GraphState.messages`

2. **Synthesis (Join Node):**
   - TieredSynthesizerSpecialist reads temporary artifacts
   - Formats final user-facing response
   - Creates **single** AIMessage containing formatted content
   - This message is appended to `GraphState.messages`

#### **Progenitor Implementation**

```python
# ProgenitorAlphaSpecialist and ProgenitorBravoSpecialist
class ProgenitorSpecialist(BaseSpecialist):
    def _execute_logic(self, state: GraphState) -> dict:
        # LLM invocation using state["messages"] for full conversation context
        response = self.llm_adapter.generate(
            messages=state["messages"],
            system_prompt=self.system_prompt
        )
        
        # CRITICAL: Write to artifacts, NOT to messages
        return {
            "artifacts": {
                "alpha_response": response.content  # or "bravo_response"
            }
            # DO NOT return "messages" key here
        }
```

#### **TieredSynthesizerSpecialist Implementation**

```python
class TieredSynthesizerSpecialist(BaseSpecialist):
    def _execute_logic(self, state: GraphState) -> dict:
        # Retrieve responses from artifacts
        alpha_response = state.get("artifacts", {}).get("alpha_response")
        bravo_response = state.get("artifacts", {}).get("bravo_response")
        
        # Handle graceful degradation (as per Part 1)
        if alpha_response and bravo_response:
            # Standard tiered format (Option B: Transparent Tiered)
            formatted_response = f"""## Perspective 1 (Alpha)
{alpha_response}

## Perspective 2 (Bravo)
{bravo_response}"""
            response_mode = "tiered_full"
        
        elif alpha_response:
            formatted_response = f"""## Response (Single Perspective)
{alpha_response}

*Note: Second perspective unavailable due to system error.*"""
            response_mode = "tiered_alpha_only"
        
        elif bravo_response:
            formatted_response = f"""## Response (Single Perspective)
{bravo_response}

*Note: Primary perspective unavailable due to system error.*"""
            response_mode = "tiered_bravo_only"
        
        else:
            # Complete failure
            raise ValueError("No progenitor responses available")
        
        # Create the single AIMessage for history
        ai_message_for_history = AIMessage(
            content=formatted_response,
            name="TieredSynthesizerSpecialist"
        )
        
        # CRITICAL: Return the single message for history
        return {
            "messages": [ai_message_for_history],  # Appended to GraphState.messages
            "scratchpad": {"user_response_snippets": [formatted_response]},
            "task_is_complete": True,
            "artifacts": {"response_mode": response_mode}
        }
```

### **GraphState Structure**

No modifications required. Existing structure supports this model:

```python
class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: dict
    artifacts: dict
    routing_decision: str
    task_is_complete: bool
```

### **Token Economics**

**Growth Analysis:**
- Average user message: 100 tokens
- Average progenitor response: 500 tokens each
- Average synthesized response: 800 tokens (formatted)
- **Growth rate: ~900 tokens/turn**

**Sustainability:**
- Turn 5: 100 + (4 × 900) + 100 = 3,800 tokens
- Turn 10: 100 + (9 × 900) + 100 = 8,200 tokens
- Turn 20: 100 + (19 × 900) + 100 = 17,300 tokens

This is highly sustainable within modern 128k context windows. Standard summarization/truncation strategies can be applied if needed for very long conversations.

### **Risk: Perspective Collapse**

**Description:** The primary risk of unified history. Progenitors may converge on consensus or engage in meta-commentary ("As Alpha mentioned...").

**Mitigation Strategies (Critical):**

1. **Rigorous Prompt Engineering:**
   - Progenitor system prompts must explicitly forbid meta-commentary
   - Emphasize maintaining unique persona, role, and analytical framework
   - Use history solely for contextual understanding, not for referencing other perspectives

2. **Model Diversity:**
   - Use fundamentally different underlying models (e.g., Gemini and Claude)
   - Leverage inherent differences in reasoning patterns and training biases

3. **Distinct Personas:**
   - Define strong, contrasting roles (e.g., Technical Expert vs. Conceptual Thinker)
   - Encode role identity deeply in system prompts

### **Context Window Management**

**When Limits Approached:**
- Implement summarization of early turns before Router execution
- Because history is unified, summarization applies globally
- Both progenitors receive identical, summarized context
- Maintains coherence while managing token budget

---

## Model-Agnostic Architecture

### **Key Principle**

The entire tiered chat architecture can be implemented with ANY model configuration. Concrete model bindings are runtime configuration, not architectural constraints.

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

---

## Monitoring and Observability

### **Metrics to Track**

1. **Response Mode Distribution:**
   - Track frequency of: tiered_full, tiered_alpha_only, tiered_bravo_only, single_fallback
   - Alert if degraded modes exceed threshold

2. **Perspective Divergence Score (Advanced):**
   - Use embedding models to measure semantic distance between Alpha and Bravo responses
   - Decreasing score over multiple turns indicates perspective collapse
   - Alert if divergence falls below threshold

3. **Meta-Commentary Rate:**
   - Track frequency of progenitors referencing each other
   - Target: 0%
   - Pattern matching: "As [Alpha/Bravo] mentioned", "The other perspective", etc.

4. **Context Growth Rate:**
   - Monitor tokens added per turn
   - Target: ~900 tokens/turn
   - Alert if growth significantly exceeds expectation

5. **Conversation Length:**
   - Track average and maximum turn counts
   - Identify patterns requiring context summarization

### **LangSmith Visualization**

- Verify progenitor nodes receive previous turn's synthesized AIMessage as input
- Confirm only Synthesizer appends to messages list during subgraph execution
- Track parallel execution timing and token consumption

### **Archive Report**

- `GraphState.messages` provides accurate archive of conversation as user experienced it
- Include `response_mode` metadata for each turn
- Include `routing_mode` (tiered_parallel vs single_chat) for each turn

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

### Progenitor Specialists
- [ ] Create ProgenitorAlphaSpecialist and ProgenitorBravoSpecialist
- [ ] Implement state management pattern (write to artifacts only)
- [ ] Develop anti-collapse system prompts (forbid meta-commentary)
- [ ] Define distinct personas (Technical vs Conceptual)
- [ ] Create prompt files: progenitor_alpha_prompt.md, progenitor_bravo_prompt.md

### TieredSynthesizerSpecialist
- [ ] Implement as procedural specialist (non-LLM)
- [ ] Check for alpha_response and bravo_response in artifacts
- [ ] Format output based on available responses (graceful degradation)
- [ ] Add explanatory notes for degraded modes
- [ ] Create single AIMessage with formatted content
- [ ] Append to GraphState.messages
- [ ] Write to scratchpad.user_response_snippets
- [ ] Return task_is_complete: True
- [ ] Include response_mode in artifacts

### Configuration Files
- [ ] Add tiered_chat section to config.yaml
- [ ] Add progenitor bindings to user_settings.yaml
- [ ] Document configuration hierarchy
- [ ] Add example configurations (dev/hybrid/production)

### API Modifications
- [ ] Add tiered_chat_enabled to request schema
- [ ] Add response_mode to response schema
- [ ] Document API parameter in OpenAPI spec
- [ ] Implement configuration priority logic

### UI Modifications
- [ ] Add "Enable Multi-Perspective Chat" toggle to settings
- [ ] Persist preference to user profile
- [ ] Show response_mode indicator in chat UI
- [ ] Add explanatory tooltip for feature
- [ ] Visual differentiation for Perspective 1/2 in rendered output

### Observability
- [ ] Add structured logging with routing_mode
- [ ] Ensure LangSmith traces show parallel execution
- [ ] Include response_mode in Archive Report
- [ ] Implement perspective divergence scoring
- [ ] Implement meta-commentary detection
- [ ] Add monitoring dashboards for key metrics
- [ ] Configure alerts for degraded modes and perspective collapse

### Documentation
- [ ] Update DEVELOPERS_GUIDE.md with Virtual Coordinator pattern
- [ ] Add ASCII diagram of routing flow
- [ ] Document state management pattern with code examples
- [ ] Add multi-turn context strategy explanation
- [ ] Document model binding examples
- [ ] Add troubleshooting section for degraded modes
- [ ] Document anti-collapse prompt engineering strategies

### Testing
- [ ] Unit tests for graceful degradation scenarios
- [ ] Integration tests for virtual coordinator routing
- [ ] Tests for configuration priority hierarchy
- [ ] Tests for all response_mode states
- [ ] Multi-turn conversation tests (5, 10, 20 turns)
- [ ] Cross-referencing scenario tests
- [ ] Contradiction handling tests
- [ ] Load tests with progenitor failures
- [ ] Token growth measurement tests
- [ ] Perspective collapse detection tests

---

## Success Criteria

- [ ] Router can choose "chat_specialist" via normal tool calling
- [ ] When tiered enabled, parallel execution occurs automatically
- [ ] When tiered disabled, single ChatSpecialist works as before
- [ ] Partial progenitor failures result in degraded but functional output
- [ ] Multi-turn conversations maintain coherence across 10+ turns
- [ ] Progenitors can respond intelligently to cross-referencing queries
- [ ] Perspective divergence remains above threshold across multiple turns
- [ ] Meta-commentary rate remains at or near 0%
- [ ] Token growth stays within ~900 tokens/turn
- [ ] Response metadata clearly indicates operational mode
- [ ] LangSmith traces show actual execution path
- [ ] No graph compilation errors
- [ ] API boolean toggle controls feature per-request
- [ ] UI preference persists across sessions
- [ ] Model bindings can be changed without code modifications

---

## Migration Path

**Phase 1: Immediate Implementation**
- Implement CORE-CHAT-002 infrastructure with all components
- Deploy initial anti-collapse prompt mitigations
- Enable basic monitoring (response_mode, token growth)

**Phase 2: Optimization and Monitoring**
- Analyze production data for perspective collapse
- Implement advanced monitoring (divergence scoring, meta-commentary detection)
- Iteratively refine progenitor prompts based on empirical data
- A/B test different model combinations

**Phase 3: Full Solution**
- Extend pattern to CORE-CHAT-003 (Diplomatic Process)
- Implement context summarization for very long conversations
- Optimize based on production learnings

---

## Related ADRs

- **CORE-CHAT-001:** Foundational ChatSpecialist (prerequisite)
- **CORE-CHAT-003:** Diplomatic Chat Subgraph (will use same state management pattern with Option A - Unified Synthesized History)

---

**Approved By:** [Project Lead]  
**Implementation Target:** Phase 1 - Pre-Production  
**Last Updated:** 2025-11-05
