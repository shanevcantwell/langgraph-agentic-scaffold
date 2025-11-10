# Testing Strategies Seed Prompts

## Domain: Testing Multi-Agent Systems and LLM-Based Components

This file contains seed prompts for generating training data about testing strategies, mocking patterns, and quality assurance for agentic systems.

### Seed Prompts (10 initial)

1. Explain the difference between unit testing individual specialists vs. integration testing multi-specialist workflows.

2. How do you design mocks for LLM adapters that provide realistic test coverage without API costs?

3. What are best practices for using centralized fixtures (initialized_specialist_factory) to prevent test suite drift?

4. Describe strategies for testing non-deterministic LLM behavior while maintaining reproducible test results.

5. How do you test error handling paths when LLMs return malformed responses or invalid tool calls?

6. What patterns help test routing logic without needing to execute full specialist implementations?

7. Explain how to use contract tests to validate all LLM adapters implement required interfaces consistently.

8. How do you test parallel execution patterns where multiple specialists run concurrently?

9. Describe strategies for testing state transformations across multi-turn workflows with 10+ specialist invocations.

10. What are effective approaches for testing observability features (LangSmith integration, logging, archival)?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
