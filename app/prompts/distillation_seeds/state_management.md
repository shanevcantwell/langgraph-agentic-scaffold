# State Management Seed Prompts

## Domain: Graph State Patterns and Best Practices

This file contains seed prompts for generating training data about state management in LangGraph workflows, state reducers, and data flow patterns.

### Seed Prompts (10 initial)

1. Explain the difference between using `operator.add` vs `operator.ior` reducers in LangGraph GraphState definitions.

2. How do you design state fields to enable parallel execution of multiple specialist nodes without conflicts?

3. What are the best practices for organizing state into artifacts (structured outputs), scratchpad (transient data), and messages (permanent history)?

4. Describe the state purge pattern and when to migrate specialist-specific fields from root state to nested dictionaries.

5. How do you prevent state bloat when accumulating large amounts of data (e.g., 10K responses) in a long-running workflow?

6. What are the trade-offs between storing data in GraphState vs. writing to external files via MCP services?

7. Explain how to use TypedDict for strongly-typed state management while maintaining flexibility for future extensions.

8. How do you handle state versioning and backwards compatibility when adding new fields to GraphState?

9. Describe patterns for state hygiene: preventing cross-contamination between unrelated workflow executions.

10. What are effective strategies for debugging state transformation bugs in multi-specialist workflows?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
