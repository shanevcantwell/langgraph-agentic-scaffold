# Deep Research Implementation Plan: Falsification Analysis

## Purpose

This document challenges the assumptions in the Deep Research Implementation Plan to identify failure modes before implementation. The goal is not to reject the plan, but to ensure it survives contact with reality.

---

## CORE QUESTION (Must Be Answered Before Implementation)

**Is the Deep Research plan building toward the Cathedral and Codex vision, or is it a scoped subset of "research task execution"?**

This question determines the architectural approach for the entire implementation.

### If Building Toward Cathedral:

The plan must include hooks for:
- **Charter consultation** before research (Blueprint 4, 8)
- **Librarian curation** of user context onto the Lectern (Blueprint 6)
- **Theory of Mind** state assessment (Companion Branch 3: Meta-ToM)
- **Whetstone Process** iterative refinement loops
- **ICSP Protocol** intervention points for challenging assumptions
- **Artifact creation** in the Codex hierarchy (Daily Annals → Case Law → Treatises)
- **Guild of Judges** alignment audit of research outputs (Blueprint 9)

### If Scoped Subset:

Explicitly label as "Research Task Execution" and defer:
- Memory/Charter integration to future work
- Whetstone iterative loops
- ToM-informed presentation
- ICSP friction protocols

This is valid - primitives can be built first, partnership layer added later. But the architecture must not preclude future integration.

### Reference Documentation

**Cathedral and Codex Vision** (`docs/PLANS/cathedral-and-codex/`):

| Document | Key Concepts |
|----------|--------------|
| `01_BLUEPRINTS/The Architect's Blueprint_ A Phased Construction Plan.md` | Tech Tree for cognitive architecture; Guilds of Librarians (B6), Strategists (B7), Judges (B9); Codex hierarchy |
| `01_BLUEPRINTS/ROADMAP_CATHEDRAL-v3.0_The-Governed-Exoskeleton.md` | Strategic priorities; Diplomatic Router; Memory Governance; Cognitive Cycle |
| `01_BLUEPRINTS/VISION_ Companion and Observatory Cognitive Memory Architecture.md` | Dynamic Memory System; State-Based Resonance; Meta-ToM (Branch 3); Bayesian Value System |
| `VISION-CATHEDRAL-001_The-Hybrid-Cognitive-Engine.md` | Cognitive co-processors; ToM Signal Processor; Alignment Kernel; Causal Inference Engine |
| `ADR-EDUCATION-001_ The Whetstone Process.md` | Four-step iterative sharpening; "Your thought is the blade, the AI is the whetstone" |
| `VISION_ The Internal Cognitive Sparring Partner_ A Protocol for Benevolent Friction.md` | ICSP Protocol; Tiered Intervention (Curious Skeptic → Loyal Opposition → Internal Mirror); Forgiveness Framework |

**Emergent State Machine** (`docs/ADRs/proposed/emergent_state_machine/`):

| Document | Key Concepts |
|----------|--------------|
| `DESIGN SPECIFICATION_ ESM-Foundry Core Architecture.md` | BaseRouter; RouterDecision; ExecutionController; Dynamic routing mechanism |
| `ROADMAP_ Emergent State Machine (ESM).md` | HIL Execution Strategy; Autonomous Loop Strategy; BaseCheckpointer; TerminationConditions |

### The "news I should care about" Query in Cathedral Framing

| Step | Cathedral Component | Reference |
|------|---------------------|-----------|
| 1. Consult Charter | Librarians place Charter sections on Lectern | Blueprint 6, 8 |
| 2. Assess user state | Meta-ToM evaluates cognitive/emotional state | Companion Branch 3 |
| 3. Plan research | Strategists formulate approach based on Case Law | Blueprint 7 |
| 4. Execute search | WebSpecialist (primitive) fetches | Deep Research Plan Phase 1 |
| 5. Challenge assumptions | ICSP intervention if findings contradict values | ICSP Protocol Level 1-2 |
| 6. Synthesize with values | Connect findings to user's stated goals | Whetstone Step 2-3 |
| 7. Audit alignment | Guild of Judges reviews output against Charter | Blueprint 9 |
| 8. Create artifact | Record as Case Law in Codex | Blueprint 7, 10 |

**Question for Gemini**: Which of these steps are in scope for the Deep Research plan, and which are explicitly deferred? The answer shapes every subsequent architectural decision.

---

## Falsification 1: The SystemsArchitect God Object

**Claim**: The SystemsArchitect can plan research, code, and builds by being "aware" of all primitives.

**Challenge**: This creates a prompt that must:
- Know all primitive capabilities and constraints
- Decide which primitives apply to which subproblems
- Sequence operations correctly
- Handle partial capability matches

**Failure mode**: As primitives grow (WebSpecialist, DataExtractor, Summarizer, CodeSpecialist, BuildRunner, future tools), the Architect prompt becomes:
1. Too long → context window pressure
2. Too complex → hallucinated capabilities ("I'll use the ImageProcessor to...")
3. Too brittle → adding one primitive requires re-tuning the whole prompt

**Question for Gemini**: At what primitive count does the Architect prompt become unmanageable? What's the escape hatch when a query spans capabilities the Architect can't reliably compose?

---

## Falsification 2: "Zero LLM Cost" is Misleading

**Claim**: WebSpecialist has "zero LLM cost" because it's just API calls.

**Challenge**: Someone must decide:
- Which search strategy (DDG vs Tavily vs Google)?
- How many results are enough?
- Whether results are relevant before passing downstream?
- When to paginate vs stop?

**Failure mode**: If these decisions are pushed to the Architect:
- Architect can't see results until after WebSpecialist returns
- Architect must guess strategy upfront
- Wrong strategy = wasted API call + retry loop

If these decisions are embedded in WebSpecialist:
- It's not "zero LLM" anymore
- Or it's hardcoded heuristics that won't generalize

**Question for Gemini**: Who makes the "is this result relevant?" judgment? If it's the Synthesizer, what happens when Synthesizer receives 10 pages of irrelevant HTML? Does it hallucinate relevance or correctly report "no useful data found"?

---

## Falsification 3: The Progressive Deep Dive Statefulness Gap

**Claim**: The system handles "What are the top 3 headlines?" → "Browse the second one."

**Challenge**: This requires:
1. Storing the 3 headlines with stable references
2. Resolving "the second one" to a specific URL
3. Maintaining ordinal indexing across conversation turns

**Failure mode**:
- If headlines are in `scratchpad`, how does the Router know to look there?
- If headlines are in `artifacts`, what's the schema?
- "The second one" requires coreference resolution - who does this?

**Question for Gemini**: Show the exact state structure after "What are the top 3 headlines?" returns. Where is "headline 2 = [URL]" stored, and what prompt/code resolves "browse the second one" to that URL?

---

## Falsification 4: The Data Pipeline Has No Conductor

**Claim**: Scenario 2.2 flows: Search → Browse → Extract → Summarize

**Challenge**: The Architect *plans* this pipeline, but who *executes* it?

Options:
1. **Router executes sequentially** - But Router is stateless per-hop. It doesn't know "we're on step 3 of 4."
2. **Architect re-plans each step** - Expensive (4 Architect calls) and risks plan drift.
3. **New "Plan Executor" node** - Not in the plan. Significant new component.

**Failure mode**: After step 2 (Browse), the system returns to Router. Router sees "user wants CRM comparison" and... routes to Architect again? Repeats Browse? There's no "continue plan from step 3" mechanism.

**Question for Gemini**: Trace exactly what happens after WebSpecialist (Browse) returns HTML. Who receives it? Who decides "now call DataExtractor"? Show the graph edges.

---

## Falsification 5: CriticSpecialist Scope Creep

**Claim**: "Update CriticSpecialist to route revisions dynamically."

**Challenge**: CriticSpecialist now must:
- Evaluate quality of output (original job)
- Determine what TYPE of work it is (plan? code? research?)
- Know which specialist handles revisions for that type
- Route correctly

**Failure mode**: CriticSpecialist becomes a second Router with domain-specific routing logic. This creates:
- Two places routing decisions are made
- Potential for CriticSpecialist and Router to disagree
- CriticSpecialist prompt complexity explosion

**Question for Gemini**: Why does CriticSpecialist need to route? Why can't it return `{approved: false, critique: "..."}` and let Router handle routing based on the critique content?

---

## Falsification 6: No Escape Hatches

**Claim**: The plan describes happy paths only.

**Challenge**: What happens when:
- Search returns zero results?
- Browse times out or returns 403?
- DataExtractor can't parse the HTML structure?
- Synthesizer's context overflows with too much input?
- Architect plans a step using a non-existent primitive?

**Failure mode**: Without explicit escape hatches, the system will:
- Hallucinate results ("Based on the search..." when search failed)
- Loop infinitely (retry the same failing step)
- Produce confident garbage (Synthesizer summarizes error messages)

**Question for Gemini**: Add an "Escape Hatch Protocol" section to each phase. What does WebSpecialist return when search fails? What does Architect do when it receives that failure signal?

---

## Falsification 7: The "Best" Judgment Problem

**Claim**: Scenario 2.3 finds "the best PDF library."

**Challenge**: "Best" requires criteria. The user didn't specify:
- Best for what? (speed, accuracy, features, maintenance)
- Best for their specific use case (which is unstated)?

**Failure mode**: Architect will either:
- Hallucinate criteria ("I'll find the most popular one")
- Pick arbitrarily ("pdfplumber is best" - based on what?)
- Ask the user (but the flow doesn't show an ask_user step)

**Question for Gemini**: Add explicit handling for underspecified queries. Does the Architect ask for criteria, or apply defaults? If defaults, what are they and where are they documented?

---

## Falsification 8: Tool Node vs Conversation Node is Undefined

**Claim**: "Wire WebSpecialist as a Tool Node, not a Conversation Node."

**Challenge**: The plan doesn't define these terms. In LangGraph:
- Is a "Tool Node" a subgraph? A function call? A different node type?
- Does "Conversation Node" mean it participates in message history?
- What's the invocation pattern difference?

**Failure mode**: Implementer interprets this differently than intended. WebSpecialist ends up as a full specialist with prompts and context, or as a raw function with no error handling.

**Question for Gemini**: Define "Tool Node" precisely. Show the LangGraph node definition for WebSpecialist vs a Conversation Node like ChatSpecialist. What's different in the `add_node()` call?

---

## Falsification 9: Parallel Execution is Afterthought

**Claim**: Phase 4 mentions "Parallel Execution" as future work.

**Challenge**: If the Phase 1-3 architecture assumes sequential execution, adding parallelism later requires:
- Changing how Architect expresses plans (sequential list → DAG)
- Changing how results are collected (single return → gather pattern)
- Changing how errors are handled (fail-fast → partial success)

**Failure mode**: Parallelism becomes a rewrite, not an extension. The "simple sequential" design becomes tech debt.

**Question for Gemini**: Should the plan structure support parallelism from the start, even if execution is initially sequential? What's the cost of designing for parallelism now vs retrofitting later?

---

## Falsification 10: The Reasonable Agent Test Applied

**Final challenge**: Does this plan pass the test:

> *"Is implementing [X] as agentic behavior preferable to a couple bespoke scripts?"*

| Component | Judgment Required? | Agentic Justified? |
|-----------|-------------------|-------------------|
| WebSpecialist (fetch) | No | ✓ Correctly made tool-like |
| WebSpecialist (choose strategy) | Maybe | ⚠️ Who decides DDG vs Tavily? |
| Architect (plan pipeline) | Yes | ✓ Core agentic value |
| DataExtractor (parse HTML) | Depends on HTML | ⚠️ Predictable HTML = script, unpredictable = agentic |
| Synthesizer (summarize) | Yes | ✓ Judgment required |
| CriticSpecialist (route revisions) | No - deterministic | ❌ Should be Router's job |

**Question for Gemini**: For each ⚠️ and ❌, either justify why agentic implementation is correct, or redesign to make it script-like.

---

## Related Concern: Process Coherence and ESM

The falsifications above (particularly #3 Statefulness and #4 No Conductor) point to a missing capability: **process coherence across multi-step workflows**.

The Emergent State Machine (ESM) concept in `docs/ADRs/proposed/emergent_state_machine/` addresses this orthogonally:

| ESM Concept | Relevant Falsification |
|-------------|------------------------|
| `BaseCheckpointer` - State persistence | #3 - Where are headlines stored? |
| `ExecutionController` with strategies | #4 - Who executes the pipeline? |
| `RouterDecision.next_node` | #5 - Single routing authority |
| HIL interrupt/resume pattern | #3 - Multi-turn conversational state |

**This is NOT a recommendation to merge ESM into the Deep Research plan.** ESM is its own architectural concern. However, an `ESMProcessManager` or similar component could potentially provide the coherence layer that the Deep Research plan currently lacks.

**Question for Gemini**: If the Deep Research plan proceeds without ESM integration, how will multi-step pipeline execution maintain coherence? If it DOES integrate ESM concepts, which specific mechanisms (Checkpointer? ExecutionStrategy?) are needed and which are out of scope?

---

## Recommendation

Before implementation, address:

1. **Define the plan execution mechanism** - Who runs steps 2, 3, 4 after Architect plans?
2. **Add escape hatches to every primitive** - Explicit failure signals, not silent fallbacks
3. **Bound the Architect's scope** - What happens when primitive count exceeds prompt capacity?
4. **Clarify Tool Node architecture** - Precise LangGraph patterns, not metaphors
5. **Decide parallelism stance** - Design for it now or accept retrofit cost later
6. **Clarify relationship to ESM** - Is process coherence in scope or explicitly deferred?
7. **Scope relative to Cathedral vision** - Is this "research task execution" or "cognitive partnership research"? The answer determines whether Whetstone/ICSP/ToM hooks are in scope or explicitly deferred.

---

## Falsification 11: The Cathedral Gap - Research as Task vs Partnership

**Claim**: The Deep Research plan enables research capabilities.

**Challenge**: The plan treats research as **task execution** (user asks → system fetches → system summarizes). But the Cathedral and Codex vision frames LAS as scaffolding for **cognitive partnership**:

| Cathedral Concept | What It Means for Research |
|-------------------|---------------------------|
| **Whetstone Process** | Research is iterative sharpening, not single-pass retrieval |
| **ICSP Protocol** | System should challenge user's research assumptions |
| **Theory of Mind** | Understand WHY user cares, not just WHAT they asked |
| **Forgiveness Framework** | Handle uncomfortable findings constructively |
| **Artifact Creation** | Output is durable knowledge structure, not ephemeral answer |

**Failure mode**: The plan builds a sophisticated fetch-and-summarize pipeline, but:
- No mechanism for the system to say "You asked about X, but based on your Charter, you might actually care about Y"
- No iterative refinement ("The Sharpening Stroke")
- No artifact creation beyond the immediate answer
- No integration with user values/memory to contextualize relevance

**The "news I should care about" query in the Cathedral framing:**

1. **Consult Charter/Memory** - What does user actually value? (Not in plan)
2. **Search** - WebSpecialist fetches headlines
3. **Apply ToM** - Is user in cognitive state to receive challenging news? (Not in plan)
4. **Challenge assumptions** - ICSP: "You say you care about climate, but your reading history is 80% finance" (Not in plan)
5. **Synthesize with values** - Connect findings to user's stated goals
6. **Create artifact** - Not "here's a summary" but "here's a structured brief you can act on"

**Question for Gemini**: Is the Deep Research plan building toward the Cathedral vision, or diverging from it? If the former, where do the Whetstone Process hooks go? If the latter, should this be explicitly scoped as "research task execution" separate from "cognitive partnership research"?

---

## Appendix: The Reasonable Agent Test

For reference, the test that should guide implementation decisions:

> *"Does this task require judgment that adapts to context that can't be fully specified upfront?"*

**Agentic implementation is justified when:**
1. The execution path requires judgment that can't be predetermined
2. Mid-task adaptation to unexpected results adds value
3. The "shape" of the solution emerges from the work itself

**Scripts are preferable when:**
1. The path is known/enumerable upfront
2. Errors have deterministic resolution
3. The value is in the OUTPUT, not the process

The Deep Research plan's value is in building the **judgment infrastructure** - not in solving specific research tasks, but in creating a substrate that can handle open-ended queries that don't have pre-built solutions. The falsifications above test whether that infrastructure is coherent enough to deliver on that promise.
