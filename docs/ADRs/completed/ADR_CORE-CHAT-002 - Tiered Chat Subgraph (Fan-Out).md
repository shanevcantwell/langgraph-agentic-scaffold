# ADR: CORE-CHAT-002 - Tiered Chat Subgraph (Fan-Out)

**Status:** Completed

**Prerequisite:** CORE-CHAT-001

Context:  
The foundational ChatSpecialist provides only a single perspective. To begin implementing the "Diplomatic Process", we need a mechanism to gather multiple perspectives and present them in a combined, "tiered" response (prompt --> chatbot1-(+)->chatbot2 --> user).  
Decision:  
We will deprecate the simple routing to ChatSpecialist. Instead, a "chat" prompt will now trigger a "fan-out" subgraph that runs two "Progenitor" specialists in parallel and combines their outputs using a new procedural specialist.  
**Implementation Plan:**

1. **Create Progenitor Specialists:**  
   * Create ProgenitorAlphaSpecialist and ProgenitorBravoSpecialist, following the CREATING_A_NEW_SPECIALIST.md guide. These represent the "Tribal Territories" (e.g., Gemini and Claude).  
   * Register them in config.yaml with distinct prompts (e.g., progenitor_alpha_prompt.md and progenitor_bravo_prompt.md).  
2. **Create TieredSynthesizerSpecialist:**  
   * Create app/src/specialists/tiered_synthesizer_specialist.py. This must be a **procedural specialist** (it does not use an LLM).  
   * Its _execute_logic will wait for responses from both progenitors to appear in the GraphState (e.g., in artifacts.alpha_response and artifacts.bravo_response).  
   * It will procedurally combine these two text responses into a single, formatted Markdown string (e.g., using ## Perspective 1 and ## Perspective 2).  
   * It will write this combined string to scratchpad.user_response_snippets and return task_is_complete: True.  
3. **Modify GraphBuilder:**  
   * Modify the _wire_hub_and_spoke_edges method.  
   * The RouterSpecialist's conditional edge logic (GraphOrchestrator.route_to_next_specialist) will be updated. If next_specialist == 'chat_specialist', it must now route to a *list* of nodes: ['progenitor_alpha_specialist', 'progenitor_bravo_specialist']. This executes them in parallel.  
   * Add direct, non-conditional edges from progenitor_alpha_specialist and progenitor_bravo_specialist to the tiered_synthesizer_specialist. This node acts as the "join" for the parallel execution.

Rationale:  
This architecture implements the prompt --> chatbot1-(+)->chatbot2 --> user flow. It introduces parallel execution and a "join" node (TieredSynthesizerSpecialist) that formats the final output, which is then handled by the standard EndSpecialist.

---

