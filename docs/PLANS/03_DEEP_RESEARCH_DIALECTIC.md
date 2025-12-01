# Deep Research Dialectic: The Architect's Defense

## Overview
This document serves as the **Counter-Falsification** to `DEEP_RESEARCH_FALSIFICATION.md`. It adopts a dialectical format (Challenge vs. Response) to address the architectural concerns raised regarding the **Architect-Driven Research** plan.

**The Core Thesis:** The "Deep Research" capability is not a separate agent, but a **Primitive** (the Body) that the **SystemsArchitect** (the Mind) wields. We are building the *capacity* for research first, so that the *governance* of research (Cathedral) can follow.

---

## The Core Question: Cathedral or Task?

**Challenge:** *Is this plan building toward the Cathedral and Codex vision, or is it just a scoped subset of "research task execution"?*

**Response:** It is the **Foundation for the Cathedral**.
We cannot govern what does not exist. Currently, the system *cannot* research. It has no eyes.
*   **Phase 1 (This Plan):** Build the "Primitive Layer" (WebSpecialist). This is the "Task Execution" layer. It is intentionally dumb.
*   **Phase 2 (Future):** Wrap the Primitive in the "Partnership Layer". The `SystemsArchitect` (guided by the Charter) decides *when* and *why* to use the Primitive.
*   **Conclusion:** We are building the "Hands" today so the "Conscience" has something to guide tomorrow.

---

## Dialectic 1: The God Object

**Challenge:** *The SystemsArchitect prompt will become unmanageable as it tries to know every primitive (Search, Extract, Code, Build).*

**Response:** **Abstraction, not Omniscience.**
The Architect does not need to know the API signature of every tool. It only needs to know the **Capabilities**.
*   **Current State:** The Architect knows "I can Search" and "I can Code".
*   **Future State (The Registry):** If the toolset grows too large, we will implement a **Capability Registry** (RAG for Tools). The Architect will query "What tools do I have for image processing?" and receive the relevant definitions dynamically.
*   **Escape Hatch:** If the Architect cannot plan, it falls back to the `ChatSpecialist` to ask the user for clarification.

---

## Dialectic 2: The "Zero Cost" Illusion

**Challenge:** *WebSpecialist isn't "Zero Cost" if it has to decide on strategies (DDG vs Tavily) and relevance. If you push that to the Architect, it's expensive.*

**Response:** **Configuration over Cognition.**
*   **Strategy Selection:** This is a **Configuration** concern, not a runtime decision. The `config.yaml` determines the default strategy (e.g., "Use DuckDuckGo for privacy"). The Architect doesn't choose the provider; it just says "Search".
*   **Relevance:** The `WebSpecialist` returns *raw* results (top N). It does not judge relevance. The **Synthesizer** (or Architect) judges relevance.
*   **Cost Reality:** Yes, the *judgment* costs tokens. But the *act of fetching* (the Primitive) does not. This is a massive improvement over an "Agentic Researcher" that loops 5 times just to figure out how to use Google.

---

## Dialectic 3: The Statefulness Gap

**Challenge:** *How does the system handle "Browse the second one"? Where is "the second one" stored?*

**Response:** **The Artifact is the State.**
*   **Mechanism:** When `WebSpecialist` runs, it saves results to `state["artifacts"]["search_results"]`.
*   **Resolution:**
    1.  User says "Browse the second one."
    2.  Router sends to `SystemsArchitect` (or `ChatSpecialist`).
    3.  Architect reads `state["artifacts"]["search_results"]`.
    4.  Architect sees Item #2 is `example.com`.
    5.  Architect creates a plan: `Browse("example.com")`.
*   **No Magic:** It relies on the existing `artifacts` persistence layer.

---

## Dialectic 4: The Missing Conductor

**Challenge:** *The Architect plans a pipeline (Search -> Extract -> Summarize), but who executes it? The Router is stateless.*

**Response:** **The Orchestrator is the Conductor.**
*   **The Fix:** We are adding a `check_plan_status` logic to the `GraphOrchestrator`.
*   **The Flow:**
    1.  Router -> Architect (Creates `SystemPlan`).
    2.  Orchestrator sees `SystemPlan` status is `in_progress`.
    3.  Orchestrator reads `next_step` from the plan.
    4.  Orchestrator routes *directly* to the next specialist (bypassing Router LLM).
*   **Result:** Deterministic, multi-step execution without "Planning to Plan" loops.

---

## Dialectic 5: Critic Scope Creep

**Challenge:** *Why does the Critic need to route? It should just critique.*

**Response:** **Conceded.**
*   **Adjustment:** The Critic should *not* route. It should return a `CritiqueArtifact` with `status: reject`.
*   **The Router's Job:** The `GraphOrchestrator` (via `after_critique_decider`) looks at the artifact. If `rejected`, it looks at the *source* of the artifact (e.g., `WebBuilder`) and routes back to it.
*   **Simplification:** The Critic remains a pure judge. The Orchestrator handles the logistics.

---

## Dialectic 6: Escape Hatches

**Challenge:** *What happens when Search returns zero results? The system will hallucinate.*

**Response:** **Fail Loudly.**
*   **Protocol:**
    1.  `WebSpecialist` returns `{"error": "No results found"}` or an empty list.
    2.  The `SystemPlan` has an `error_handler` field (or the Orchestrator defaults to Architect).
    3.  The Architect receives the error.
    4.  The Architect's prompt explicitly instructs: "If a step fails, do not hallucinate. Ask the user for a new direction."

---

## Dialectic 7: The "Best" Judgment

**Challenge:** *"Find the best PDF library." Best is subjective. The Architect will guess.*

**Response:** **The Whetstone Opportunity.**
*   **Current Behavior:** The Architect will likely use "Popularity" or "Recent Updates" as a proxy for "Best". This is acceptable for Phase 1.
*   **Cathedral Behavior (Phase 2):** This is exactly where the **ICSP (Internal Cognitive Sparring Partner)** intervenes.
    *   *User:* "Find the best..."
    *   *ICSP:* "Wait. 'Best' is undefined. Are you optimizing for speed or accuracy?"
    *   *System:* Asks the user.
*   **Conclusion:** We accept the "Guess" for now to enable the feature, but mark this as the primary integration point for the ICSP.

---

## Dialectic 8: Tool Node Definition

**Challenge:** *What is a "Tool Node"?*

**Response:** **LangGraph Semantics.**
*   **Definition:** A node that receives `state`, executes a Python function (no LLM), and returns `ToolMessage` or updates `artifacts`.
*   **Implementation:** It is a standard `add_node("web_specialist", web_specialist_node)`.
*   **Distinction:** It is *not* in the Router's "Conversation" prompt. The Router sees it as a capability to *use*, not a persona to *talk to*.

---

## Dialectic 9: Parallelism

**Challenge:** *Designing for sequential now makes parallel hard later.*

**Response:** **YAGNI (You Ain't Gonna Need It - Yet).**
*   **Reality:** 90% of research tasks are sequential (Search -> Read -> Synthesize).
*   **Cost/Benefit:** Implementing a DAG executor now triples the complexity of the `GraphOrchestrator`.
*   **Strategy:** We build sequential first. When we need parallelism (e.g., "Search 5 topics at once"), we will upgrade the `SystemPlan` schema and the Orchestrator. The `WebSpecialist` primitive remains unchanged.

---

## Dialectic 10: The Reasonable Agent Test

**Challenge:** *Is this agentic behavior justified?*

**Response:** **The Hybrid Verdict.**
*   **WebSpecialist:** **Tool.** (Correct).
*   **Architect:** **Agent.** (Correct - Planning requires reasoning).
*   **DataExtractor:** **Hybrid.** It uses an LLM to parse unstructured HTML, but it acts like a function. This is the "Cognitive Co-Processor" model described in the Cathedral vision.

---

## Dialectic 11: The HitL Integration

**Challenge:** *The Dialectic relies on "Fail Loudly" via prompt compliance, which is brittle. How do we guarantee the system stops when confused?*

**Response:** **Structural Interruption (ADR-CORE-018).**
We adopt the **HitL Clarification Flow**.
*   **Mechanism:** The primitive returns `clarification_required`.
*   **Enforcement:** The `GraphOrchestrator` pauses execution (`interrupt_before`).
*   **Result:** A code-enforced guarantee that the system stops for user input, rather than hoping the LLM behaves.

---

## Conclusion

The Falsification document correctly identifies the risks of **complexity** and **state drift**.
Our defense is **Structure**:
1.  **Primitives** (WebSpecialist) do the work.
2.  **Artifacts** (SystemPlan) hold the state.
3.  **Orchestrator** (Code) drives the bus.
4.  **Architect** (LLM) draws the map.

We proceed with Phase 1, explicitly acknowledging that the "Partnership" features (ICSP, ToM) are deferred until the "Hands" are working.
