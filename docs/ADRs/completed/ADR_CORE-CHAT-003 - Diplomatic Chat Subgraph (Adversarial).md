# ADR: CORE-CHAT-003 - Diplomatic Chat Subgraph (Adversarial)

**Status:** Completed

**Prerequisite:** CORE-CHAT-002

Context:  
CORE-CHAT-002 simply combines responses. It does not achieve consensus or validation. We must implement the full "Diplomatic Process" (prompt-->(chatbot1<-->chatbot2)-->Arbiter-->user). This requires an adversarial loop and a final "Arbiter" that validates the output and has direct control over the final_user_response.md. This ADR directly implements the "Diplomatic Router" concept from ROADMAP_CATHEDRAL-v3.0 and The Diplomatic Process diagram.  
Decision:  
We will replace the procedural TieredSynthesizerSpecialist with an LLM-driven DiplomaticSynthesizerSpecialist and add a new ArbiterSpecialist. The ArbiterSpecialist will function as a "Neutral Arbiter", leveraging the CriticSpecialist's ACCEPT/REVISE logic to create a consensus loop.  
**Implementation Plan:**

1. **Deprecate TieredSynthesizerSpecialist:** Remove this specialist and its routing from the GraphBuilder.  
2. **Create DiplomaticSynthesizerSpecialist:**  
   * This is an **LLM-driven specialist** (the "Synthesizer C").  
   * Its prompt instructs it to receive the two Progenitor responses and draft a single, "unified proposal".  
3. **Create ArbiterSpecialist:**  
   * This specialist's implementation will be based on the existing CriticSpecialist. It is the "Validator D" / "Neutral Arbiter".  
   * Its prompt instructs it to validate the DiplomaticSynthesizerSpecialist's "unified proposal" against "The Law of the Land" (e.g., a core principles document or the "Source of Truth").  
   * It will output a decision: ACCEPT or REVISE.  
4. **Modify GraphBuilder:**  
   * RouterSpecialist -> [ProgenitorAlphaSpecialist, ProgenitorBravoSpecialist] (Same as CORE-CHAT-002).  
   * [ProgenitorAlphaSpecialist, ProgenitorBravoSpecialist] -> DiplomaticSynthesizerSpecialist (The "join").  
   * DiplomaticSynthesizerSpecialist -> ArbiterSpecialist (The "check").  
   * **Add Consensus Loop:** Add a conditional edge from ArbiterSpecialist using the GraphOrchestrator.after_critique_decider logic:  
     * If REVISE: Route back to DiplomaticSynthesizerSpecialist. This creates the (chatbot1<-->chatbot2) loop.  
     * If ACCEPT: Route to the GraphOrchestrator.check_task_completion decider.  
5. **Fulfill Termination Constraint (Key Requirement):**  
   * The ArbiterSpecialist's _execute_logic must be modified to fulfill the user's request to "define the contents of the message returned".  
   * When the ArbiterSpecialist's decision is ACCEPT, it must:  
     1. Generate its final "Final, Ratified Artifact" text.  
     2. Write this final, user-facing text *directly* to scratchpad.user_response_snippets.  
     3. Return task_is_complete: True.  
   * **Example Return on ACCEPT:**  
     Python  
     return {  
         "messages": [ai_message_to_graph],  
         "scratchpad": {"user_response_snippets": ["...The Arbiter's Final, Ratified Artifact..."]},  
         "task_is_complete": True  
     }

Rationale:  
This implements the full adversarial loop. The EndSpecialist's response_synthesizer_specialist logic will now find the single, complete, ratified response from the ArbiterSpecialist in the scratchpad and pass it to the user as the final_user_response.md. This perfectly satisfies the requirement for the Arbiter to control the final output message.  
