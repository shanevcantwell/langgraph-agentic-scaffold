# Specialist Patterns Seed Prompts

## Domain: Specialist Design Patterns and Best Practices

This file contains seed prompts for generating training data about specialist architecture, functional decomposition, and reusable specialist patterns.

### Seed Prompts (10 initial)

1. Explain the difference between functional specialists (task-specific) and service specialists (MCP-only, no graph execution).

2. How do you decide when to split functionality into separate specialists vs. keeping it in one multi-purpose specialist?

3. What are the key principles for designing specialists that remain simple enough for open-weight models running on low-wattage hardware?

4. Describe the progenitor-synthesizer pattern and when it's preferable to single-specialist execution.

5. How do you implement specialist composition patterns where one specialist orchestrates multiple sub-specialists?

6. What strategies help prevent specialists from violating the single responsibility principle as requirements evolve?

7. Explain how to design specialists for testability using mocked LLM adapters and centralized fixtures.

8. How do you handle cross-cutting concerns (logging, error handling, observability) without code duplication across specialists?

9. Describe patterns for migrating specialist-specific state fields from root GraphState to artifacts/scratchpad dictionaries.

10. What are best practices for specialist prompt engineering to maximize output quality while minimizing token usage?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
