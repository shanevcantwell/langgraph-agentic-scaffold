# LLM Integration Seed Prompts

## Domain: LLM Adapter Patterns and Multi-Model Strategies

This file contains seed prompts for generating training data about integrating multiple LLM providers, adapter patterns, and model selection strategies.

### Seed Prompts (10 initial)

1. Explain the adapter pattern for abstracting LLM provider differences (OpenAI, Gemini, Anthropic, local models).

2. How do you design a model-agnostic architecture where specialists don't hardcode model dependencies?

3. What are the key considerations when binding different LLM models to different specialists in a single workflow?

4. Describe best practices for handling LLM provider-specific response formats (tool calls, text responses, streaming).

5. How do you implement graceful fallback when a primary LLM provider fails or rate-limits requests?

6. What strategies help optimize cost vs. quality trade-offs by using cheaper models for simple tasks and premium models for complex reasoning?

7. Explain how to extract structured data from LLM responses when providers return inconsistent JSON formatting.

8. How do you handle streaming responses from different LLM providers with varying stream formats?

9. Describe patterns for testing LLM-dependent code with mocked adapters to avoid API costs during development.

10. What are effective strategies for migrating between LLM providers without rewriting specialist logic?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
