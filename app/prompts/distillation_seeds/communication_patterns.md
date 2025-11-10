# Communication Patterns Seed Prompts

## Domain: Inter-Specialist Communication and Message Passing

This file contains seed prompts for generating training data about communication patterns, message passing protocols, and coordination mechanisms.

### Seed Prompts (10 initial)

1. Explain the differences between the Dossier pattern (asynchronous, state-mediated) and MCP (synchronous, direct service calls).

2. How do you design communication protocols that prevent cross-contamination between parallel specialist executions?

3. What are the trade-offs between using artifacts (structured outputs) vs. messages (LangChain Messages) for inter-specialist communication?

4. Describe the ranked fallback routing pattern and how it reduces expensive LLM router calls on failure.

5. How do you implement reflexive routing for simple, deterministic tasks that bypass the LLM router entirely?

6. What strategies help prevent infinite communication loops where specialists repeatedly call each other?

7. Explain how to use the scratchpad for ephemeral specialist coordination data vs. root state for persistent workflow data.

8. How do you handle communication when specialists need to accumulate large datasets (10K+ items) without state bloat?

9. Describe patterns for request-response communication between specialists that need synchronous collaboration.

10. What are best practices for versioning communication protocols when evolving specialist interfaces over time?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
