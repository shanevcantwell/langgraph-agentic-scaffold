# Observability and Debugging Seed Prompts

## Domain: System Observability, Tracing, and Debugging Techniques

This file contains seed prompts for generating training data about observability tools, debugging strategies, and production monitoring.

### Seed Prompts (10 initial)

1. Explain how LangSmith tracing enables visual inspection of multi-agent workflow execution and state transitions.

2. How do you design logging strategies that provide debugging value without overwhelming operators with noise?

3. What are the key metrics to monitor in production multi-agent systems for detecting degraded performance?

4. Describe the Atomic Archival pattern and how it creates auditable snapshots of completed workflow executions.

5. How do you implement distributed tracing to correlate events across multiple specialist invocations in a single workflow?

6. What strategies help debug state transformation bugs when specialists modify shared GraphState in unexpected ways?

7. Explain how to use structured logging (JSON logs) to enable programmatic analysis of workflow execution patterns.

8. How do you diagnose infinite loops or unproductive routing patterns in production without killing active workflows?

9. Describe techniques for debugging LLM prompt engineering issues using trace data and response analysis.

10. What are best practices for implementing health checks and readiness probes for multi-agent systems in Docker environments?

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
