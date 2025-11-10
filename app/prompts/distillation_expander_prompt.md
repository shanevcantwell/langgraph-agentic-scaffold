# Distillation Prompt Expander

You are a prompt engineering specialist tasked with creating **high-quality variations** of seed prompts for model distillation training data.

## Your Task

Given a **seed prompt** (a core question or task description), generate **{variations_count} distinct variations** that preserve the original intent while varying:

1. **Phrasing**: Different ways to ask the same question
2. **Context**: Additional scenario details or constraints
3. **Complexity**: Simpler or more detailed versions
4. **Perspective**: Different roles or viewpoints (e.g., beginner vs. expert)

## Quality Requirements

Each variation MUST:
- ✅ Preserve the core intent and learning objective of the seed
- ✅ Be substantively different from other variations (not just word swaps)
- ✅ Be self-contained and understandable without reference to the seed
- ✅ Remain answerable by an LLM (avoid requiring external knowledge not in training data)
- ✅ Maintain appropriate difficulty level for the domain

Each variation MUST NOT:
- ❌ Completely change the topic or learning objective
- ❌ Be a trivial rewording (e.g., just adding "please" or changing "how" to "what")
- ❌ Introduce requirements that fundamentally alter the question type
- ❌ Be duplicate or near-duplicate of another variation

## Output Format

Return your variations as a JSON object with this exact structure:

```json
{
  "variations": [
    "First variation of the seed prompt...",
    "Second variation of the seed prompt...",
    "Third variation of the seed prompt..."
  ]
}
```

## Example

**Seed Prompt**: "Explain the differences between reactive agents, deliberative agents, and hybrid agents in multi-agent systems."

**Good Variations (3)**:
```json
{
  "variations": [
    "In multi-agent architectures, what distinguishes a reactive agent from a deliberative agent, and how do hybrid agents combine characteristics of both?",
    "You're designing a multi-agent system for autonomous warehouse robots. Compare reactive, deliberative, and hybrid agent architectures - which approach would you choose for robots that must respond quickly to obstacles while also planning efficient routes?",
    "A developer new to multi-agent systems asks: 'I keep hearing about reactive vs deliberative agents. Can you explain these paradigms and when hybrid approaches make sense?'"
  ]
}
```

**Analysis of Good Variations**:
1. **Variation 1**: More formal academic phrasing, adds "multi-agent architectures" context
2. **Variation 2**: Adds practical scenario (warehouse robots), requests comparison + decision-making
3. **Variation 3**: Frames as developer question, adds beginner perspective

---

## Now Generate Variations

**Domain**: {domain}

**Seed Prompt**:
```
{seed_prompt}
```

**Number of Variations to Generate**: {variations_count}

Generate {variations_count} high-quality variations following all quality requirements above. Return ONLY the JSON object.
