# Agentic Architecture Seed Prompts

## Domain: Multi-Agent System Design Patterns

This file contains seed prompts for generating training data about agentic architecture patterns, multi-agent orchestration, and system design principles.

### Seed Prompts (10 initial)

1. Explain the differences between reactive agents, deliberative agents, and hybrid agents in multi-agent systems.

2. How do you design a coordinator agent that routes tasks to specialized sub-agents without becoming a bottleneck?

3. What are the key considerations when implementing a hierarchical agent architecture vs. a flat peer-to-peer architecture?

4. Describe the virtual coordinator pattern and how it enables transparent upgrades from single-node to multi-node subgraphs.

5. How do you handle state synchronization between multiple agents operating in parallel within a shared workflow?

6. What are the trade-offs between centralized routing (single router agent) and distributed routing (each agent chooses next step)?

7. Explain how to prevent infinite loops in multi-agent systems where agents can recursively call each other.

8. What architectural patterns help ensure fault tolerance when one specialist agent fails during multi-agent collaboration?

9. How do you implement graceful degradation in multi-agent systems when some agents become unavailable?

10. Describe best practices for observability and debugging in multi-agent workflows with 5+ specialists.

---

**Usage**: These seeds will be expanded into 3 variations each by DistillationPromptExpanderSpecialist, then responses collected via teacher model for distillation dataset.
