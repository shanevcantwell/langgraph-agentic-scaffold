# Deep Research Implementation Plan: The Architect-Driven Ecosystem

## Executive Summary
This plan outlines the transformation of the system's research capabilities from a rigid "Agent" model to a flexible "Architect-Driven" ecosystem. By refactoring the `ResearcherSpecialist` into a dumb `WebSpecialist` primitive and empowering the `SystemsArchitect` to plan research workflows, we unlock emergent behaviors (e.g., "Research then Code", "Search then Extract").

## Phase 1: The "3-Point Turn" (Refactor)
*Objective: Convert the Researcher from an Agent to a Tool.*

### 1.1 Revert & Clean Up
- [ ] **Revert `ResearcherSpecialist`:** Undo the partial Strategy Pattern implementation in `researcher_specialist.py` to establish a clean baseline.
- [ ] **Verify Baseline:** Ensure the system builds and runs.

### 1.2 The `WebSpecialist` (Primitive)
- [ ] **Rename:** Rename `ResearcherSpecialist` to `WebSpecialist`.
- [ ] **Strip Logic:** Remove the LLM execution loop. It becomes a pure MCP tool provider.
- [ ] **Implement Strategies:**
    - [ ] **Search:** `DuckDuckGo` (Privacy), `Tavily` (Deep), `Google` (Broad).
    - [ ] **Browse:** `Requests` (Simple), `Headless Browser` (Complex - Future).
- [ ] **Configuration:** Update `config.yaml` to register strategies.

### 1.3 The `SystemsArchitect` (Planner)
- [ ] **Prompt Update:** Expand the `SystemsArchitect` prompt to include "Research Planning".
- [ ] **Tool Awareness:** Explicitly list the ecosystem's capabilities in the prompt:
    - `WebSpecialist` (Search/Browse)
    - `DataExtractorSpecialist` (Structure Data)
    - `SummarizerSpecialist` (Condense Info)
    - `CodeSpecialist` (Execute Logic)

### 1.4 The Router & Wiring
- [ ] **Update Graph:** Wire `WebSpecialist` as a Tool Node, not a Conversation Node.
- [ ] **Dynamic Critique:** Update `CriticSpecialist` to route revisions dynamically (e.g., critique a Plan -> send to Architect; critique Code -> send to Coder).

---

## Phase 2: Integration Scenarios (The "What-Ifs")
*Objective: Verify that the Architect can orchestrate the primitives to solve complex problems.*

### 2.1 The Progressive Deep Dive
*   **User:** "What are the top 3 headlines in AI?" -> "Browse the second one." -> "Write a report on its implications."
*   **Flow:** `Router` -> `WebSpecialist` (Search) -> `WebSpecialist` (Browse) -> `SystemsArchitect` (Plan Report) -> `Synthesizer`.

### 2.2 The Data Pipeline (Ecosystem Test)
*   **User:** "Find pricing for 5 CRM tools, extract features to JSON, and summarize differences."
*   **Flow:**
    1.  `SystemsArchitect`: Plans the pipeline (Search -> Browse -> Extract -> Summarize).
    2.  `WebSpecialist`: Fetches raw HTML.
    3.  `DataExtractor`: Converts HTML to JSON.
    4.  `Summarizer`: Consumes JSON, produces text.

### 2.3 The "Tech Stack" Selection (Research + Code)
*   **User:** "Find the best PDF library and write a demo script."
*   **Flow:**
    1.  `SystemsArchitect`: Plans research.
    2.  `WebSpecialist`: Finds `pdfplumber` docs.
    3.  `CodeSpecialist`: Writes script using the *actual* docs found.

---

## Phase 3: Model & Cost Analysis
*Objective: Optimize for performance and budget.*

### 3.1 The "Headline Analysis" Cost Model
*Task: "Check headlines against my values."*

| Step | Component | Model | Reasoning |
| :--- | :--- | :--- | :--- |
| 1 | Router | Qwen-2.5-32B | High reasoning to detect "Research" intent. |
| 2 | Architect | Qwen-2.5-32B | Complex planning required. |
| 3 | WebSpecialist | N/A | **Zero LLM Cost** (API only). |
| 4 | Synthesizer | Mistral-Nemo-12B | High context for reading results. |

**Total:** ~3 High-Intelligence Calls + 1 High-Context Call.

### 3.2 Recommendation
*   **Orchestration (Router/Architect):** Stick to 30B+ parameter models (Qwen, Llama-3-70B) for reliability.
*   **Synthesis:** Use 12B-20B models with large context windows (Mistral-Nemo, Yi) to process search results cheaply.

---

## Phase 4: Future Roadmap
*   **Headless Browser Strategy:** Add a Selenium/Playwright strategy to `WebSpecialist` for JS-heavy sites.
*   **Memory Integration:** Allow the Architect to query Long-Term Memory before planning research.
*   **Parallel Execution:** Allow the Architect to spawn multiple `WebSpecialist` calls in parallel (Scatter-Gather).
