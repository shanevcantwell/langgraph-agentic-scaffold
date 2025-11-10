# Error Handling Seed Prompts

## Domain: Progressive Resilience and Fault Tolerance

This file contains seed prompts for generating training data about error handling strategies, progressive resilience patterns, and system stability.

### Seed Prompts (10 initial)

1. Explain the four-tier progressive resilience architecture: tactical retry, heuristic repair, escalated recovery, strategic oversight.

2. How do you implement fail-fast validation at startup to prevent running in broken, partially-functional states?

3. What are the differences between handling syntactic failures (malformed JSON) vs semantic failures (incorrect reasoning)?

4. Describe the self-correction signal pattern and how specialists request retries with clarifying prompts.

5. How do you implement circuit breaker patterns in multi-agent workflows to prevent cascading failures?

6. What strategies help distinguish between recoverable errors (retry worthy) and terminal errors (fail immediately)?

7. Explain how to implement graceful degradation when optional specialists fail vs. when critical specialists fail.

8. How do you design error messages that provide actionable diagnostics without exposing sensitive system internals?

9. Describe patterns for logging and observability that help debug errors in production without overwhelming operators.

10. What are best practices for handling LLM format compliance failures (JSON parsing, tool call validation, response structure)?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
