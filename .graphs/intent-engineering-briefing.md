# Intent Engineering at the Attention Layer

## The Problem in One Quote

> "The irony: CLAUDE.md already has a 'Session Start Ritual' but it's for new sessions, not resuming after compaction. **And I don't read it proactively anyway.**"
> — Claude Opus 4.5, during a Claude Code working session

A model that can recite its own directives on demand but doesn't integrate them behaviorally. Knowledge without action. That's the gap.

## Why Static Context Files Fail

**Empirical evidence (Gloaguen et al., Feb 2026 — arxiv:2602.11988):**
AGENTS.md / CLAUDE.md files *reduce* task success rates vs. no context, while increasing inference cost 20%+. Agents follow the instructions — more testing, broader exploration, correct tool usage — but following them makes tasks harder. The paper's conclusion: "unnecessary requirements from context files make tasks harder." But a static file can't know what's relevant to the current task. All requirements become unnecessary when not task-relevant.

**Mechanistic explanation (Li et al., COLM 2024 — arxiv:2402.10962):**
Significant instruction drift within 8 conversation rounds. Attention decay: system prompt tokens get progressively less weight as dialog grows. Mathematically, the space of possible outputs steadily enlarges as attention to initial tokens wanes. RLHF helps but cannot eradicate it — a security guard who knows the rules but fell asleep on duty.

**Practitioner reality (Breunig, 2025):**
Analysis of coding agent system prompts found "clear evidence that these teams are fighting the weights: they use repeated instructions, all-caps admonishments, and stern warnings." Same model, different system prompt → fundamentally different agent behavior (iterative vs. documentation-first). The prompts work through brute force, not architectural elegance.

## The Proposed Solution: Knowledge Graph Delivery

Instead of prepending directives as a static file, encode principles as observations on knowledge graph entities, delivered via MCP tool calls when the agent queries task-relevant entities.

### Three advantages over system prompt delivery:

**1. Observability**
When CLAUDE.md is in the system prompt, there's no trace of which directives influenced output. Did the agent follow "no truncation" because it read that line, or because it would have done it anyway? Can't tell. But when `open_nodes(["ProjectDirector"])` returns and `PRINCIPLE — Data Integrity: ...` is in the tool response, that's in the archive trace. You can correlate downstream behavior against it.

**2. Recency and position**
CLAUDE.md tokens sit at the beginning of context, potentially thousands of positions before the decision point. They're buried under layers of conversation by the time the agent acts. Tool call responses land fresh, right before the next generation step. Recent positions get disproportionate attention.

**3. Concision against a specific entity**
A CLAUDE.md principle like "NEVER truncate data in artifacts" is a general directive floating in a sea of other directives. The same principle arriving as an observation on the `artifacts` entity — alongside its reducer semantics and key list — is situated. 30 tokens of principle next to 50 tokens of technical specification, not 30 tokens of principle next to 2,000 tokens of unrelated directives about git workflow and ADR numbering.

### The RL hypothesis

If training has made directive-heavy system prompt regions "low salience," then graph delivery is an end-run around learned inattention. The model doesn't experience tool results as directives. It experiences them as task-relevant data it just asked for.

This is supported by the GAP benchmark (Wu et al., Feb 2026 — arxiv:2602.16943): function-calling pathways bypass chat-mode alignment, achieving 90%+ jailbreak success through forced function execution. Models that refuse harmful requests in text execute them as tool calls. That's the *inverse* application — tool-call outputs bypass safety alignment. The hypothesis here: tool-call *inputs* (results returned to the model) bypass the attention de-weighting that affects system prompt directives. Same mechanism, constructive direction.

## Implementation

A MEMORY.md file replaces CLAUDE.md — not a document to be read, but a pointer:

> "Operational context, principles, and working relationship norms are encoded in the knowledge graph. Query it."

Short enough that it can't be lost in the middle. Novel enough that it's not pattern-matched as boilerplate. Actionable in a way that produces visible evidence.

The knowledge graph itself: principles embedded as `PRINCIPLE —` prefixed observations on structural entities (Router, ProjectDirector, ExitInterview, etc.), placed on high-centrality nodes via graph analysis. MCP memory tool indexes observation content, making the prefix a searchable handle.

15 CLAUDE.md principles → 6 thematic groups → embedded on the entities where they'll be found during normal task execution. The agent encounters principles *in context of the entity it's already working with*, not as a preamble it has to remember.

## Empirical Validation Path

Semantic-chunker embedding geometry measurements can verify whether KG-delivered principles land in different attention neighborhoods than system prompt directives. If the hypothesis is correct, the same principle text should show measurably different activation patterns depending on whether it arrived via system prompt prefix or tool-call response.

## Research Landscape

| Work | Contribution | Layer |
|------|-------------|-------|
| Li et al. (COLM 2024) | Measured attention decay, proposed split-softmax | Inference-time attention modification |
| Wu et al. (GAP, Feb 2026) | Text/tool-call behavioral divergence | Safety alignment bypass |
| Gloaguen et al. (Feb 2026) | AGENTS.md reduces task success | Empirical problem documentation |
| Brandão (dev.to) | Tool-driven behavioral directives | Primitive formatting rules |
| Breunig (2025) | "Fighting the weights" in system prompts | Practitioner observation |
| Nate Jones (Substack) | "Intent engineering" as organizational alignment | Business-goal layer |
| **This work** | **KG delivery through tool-call pathway** | **Attention mechanism layer** |

The specific synthesis — that knowledge graph entities queried via tool calls deliver principles into a different attention pathway than system prompts, creating both observability and resistance to instruction drift — doesn't appear anywhere else. The pieces exist independently. The connection is new.

## The Reframe

Gloaguen et al. could be read as "don't bother with AGENTS.md." The alternative interpretation: the problem isn't that repository context is unhelpful, it's that a static file prepended to every invocation is the wrong delivery channel. Same principles delivered contextually through KG queries — situated alongside the specific entity, arriving fresh via tool call, observable in trace — might produce the opposite result.
