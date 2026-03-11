### **ADR Compendium for Project Bedrock v4 Scoping**

**Objective:** To provide a synthesized, high-signal overview of all significant architectural decisions and principles established since the publication of `ROADMAP_Project_Bedrock_v3.1`. This document is the primary input for defining the scope and priorities of the next-generation roadmap.

### **Section 1: Foundational Principles (Mandates & Vision)**

These documents establish the high-level strategic intent that governs the tactical ADRs.

*   **Reference:** `MANDATE-CORE-001_The Progressive Resilience...res.md`
    *   **Architectural Principle:** **Progressive Resilience.** The system must reject the dichotomy between simple, encapsulated error handling and complex, agentic recovery. It mandates a multi-tiered approach: immediate tactical retries and heuristic repairs at the component level, with a formal escalation path to a specialized recovery sub-workflow for persistent failures.
    *   **System-Wide Impact:** Establishes a formal strategy for system-wide error handling, distinguishing between transient syntactic faults and deeper semantic failures. This provides a blueprint for building robust, self-stabilizing components.

*   **Reference:** `VISION-CORE-001 Governed, State-Aware Agenti... v2.md`
    *   **Architectural Principle:** **Governed Statefulness.** The long-term vision is to create a stateful agent with a multi-layered memory core ("Codex"). This powerful capability must be managed by a sophisticated governance layer (the "Governed Exoskeleton") featuring adversarial oversight and ethical guardrails to mitigate risks like bias amplification and sycophancy.
    *   **System-Wide Impact:** Provides the long-term "north star" for the project. All tactical decisions should be evaluated for their alignment with this vision of creating a safe, stateful, and continuously learning agent.

### **Section 2: Tactical Decisions (ADR Synthesis)**

The following ADRs represent concrete, implemented, or approved decisions that have evolved the system's architecture.

#### **Theme: System Resilience & Stability**

This group of ADRs aggressively hardens the system against common failure modes.

*   **Reference:** `ADR-CORE-001_Fail-Fast Startup Validation.md`
    *   **Architectural Principle:** **Fail-Fast Validation.**
    *   **Decision Summary:** The system will no longer tolerate silent failures of critical components during startup. A configurable list of `critical_specialists` is now checked, and the application will terminate immediately with a clear error if a required component fails to load.
    *   **System-Wide Impact:** Transforms silent, hard-to-debug runtime errors into loud, immediate startup failures, dramatically improving debuggability and preventing the system from running in a broken, partially-functional state.

*   **Reference:** `ADR-CORE-002_Standardized Specialist Self-C...ism.md`
    *   **Architectural Principle:** **Decoupled Self-Correction.**
    *   **Decision Summary:** A standardized mechanism (`self_correction_request` signal in the state) allows any specialist to flag a recoverable internal error and request a retry with a clarifying prompt. The `RouterSpecialist` is responsible for handling this signal.
    *   **System-Wide Impact:** Increases system autonomy and resilience to a common class of LLM failures (e.g., malformed output) without requiring each specialist to implement its own complex retry logic.

*   **Reference:** `ADR-CORE-006-fail-fast-on-unknown-graph-routes.md`
    *   **Architectural Principle:** **Fail-Fast on Invalid Control Flow.**
    *   **Decision Summary:** Replaces `langgraph`'s default "fail-closed" looping behavior with a strict "fail-fast" policy. Any attempt to route to a destination not in a node's explicit destination map will immediately raise a `WorkflowError`.
    *   **System-Wide Impact:** Eliminates a class of silent, infinite-loop bugs caused by routing misconfigurations, making the graph's behavior more predictable and robust.

#### **Theme: State Management & Communication**

These ADRs formalize how components communicate, moving from implicit conventions to explicit, enforceable contracts.

*   **Reference:** `ADR-CORE-003_Directed Inter-Specialist Comm...ern.md`
    *   **Architectural Principle:** **Explicit, State-Mediated Communication.**
    *   **Decision Summary:** Introduces the **Dossier Pattern**, a dedicated object in the `GraphState` that acts as a courier, explicitly defining a recipient and a data payload for a single, directed transaction between specialists.
    *   **System-Wide Impact:** Makes data-dependent routing deterministic and observable. It replaces unreliable LLM inference for routing with a clear, traceable, and robust data contract.

*   **Reference:** `ADR-CORE-004_Refinement of Dossier State Ma...ent.md`
    *   **Architectural Principle:** **State Hygiene and Runtime Integrity.**
    *   **Decision Summary:** Refines the Dossier pattern by (1) relocating the `dossier` field into the transient `scratchpad` to maintain state purity, and (2) making the `GraphOrchestrator` responsible for runtime validation of the `dossier.recipient`.
    *   **System-Wide Impact:** Hardens the system against a class of deterministic logic errors (invalid routing instructions) and reinforces the architectural separation between long-lived graph state and transient specialist state.

#### **Theme: Orchestration & Routing Intelligence**

These ADRs evolve the central router from a simple LLM call into a more sophisticated, multi-stage decision engine.

*   **Reference:** `ADR-CORE-005_Reflexive Routing for Common T...sks.md`
    *   **Architectural Principle:** **Procedural Bypass for Deterministic Tasks.**
    *   **Decision Summary:** Introduces a "reflex" mechanism in the `RouterSpecialist`. A pre-LLM procedural check attempts to match the task against a map of simple patterns to deterministic functions, bypassing the expensive LLM call for common, trivial tasks.
    *   **System-Wide Impact:** Massively reduces latency and operational costs for multi-step workflows by handling the "trivial many" tasks procedurally, freeing the LLM to focus on the "complex few."

*   **Reference:** `ADR-CORE-007-implement-ranked-fallback-routing.md`
    *   **Architectural Principle:** **Strategic Planning with Fallback.**
    *   **Decision Summary:** Evolves the router's output from a single choice to a ranked list of specialists to try (`routing_plan`). The `GraphOrchestrator` is now responsible for executing this plan, trying the next specialist in the list upon failure.
    *   **System-Wide Impact:** Increases resilience by providing automatic "Plan B" execution. It marks a significant architectural shift, moving the router from a purely reactive component to a short-term strategic planner.

#### **Theme: Foundational Platform & Observability**

These ADRs establish a professional-grade foundation for running and observing the system.

*   **Reference:** `ADR-PLATFORM-001_Unified-Container-Architecture.md`
    *   **Architectural Principle:** **Decoupled, Service-Oriented Deployment.**
    *   **Decision Summary:** Defines a formal `docker-compose` architecture with two separate services: `app` (the agent) and `db` (the PostgreSQL memory). It provides a persistent, writable filesystem for the application.
    *   **System-Wide Impact:** Establishes a robust, scalable, and maintainable local development and deployment environment, resolving critical infrastructure dependencies.

*   **Reference:** `ADR-OBS-001_System Observability and Archiv...egy.md`
    *   **Architectural Principle:** **High-Fidelity, Atomic Archival.**
    *   **Decision Summary:** Decommissions the monolithic `ArchiverSpecialist` in favor of a tool-based approach. The definitive output of a run is now an **"Atomic Archival Package"** (`.zip` file) containing a manifest, all artifacts in their native formats, and a formal contract for managing binary assets.
    *   **System-Wide Impact:** Dramatically improves the fidelity, usability, and reliability of the system's primary observability artifact. Decomposing archival logic into reusable tools for the `FileSpecialist` increases system-wide modularity and capability.

### **Section 3: Synthesis for Bedrock v4 Planning**

The collective impact of these decisions reveals several major strategic pillars that have emerged since Bedrock v3.1. These pillars should form the core themes of the next roadmap.

1.  **Pillar 1: Aggressive Resilience.** A clear theme across multiple ADRs is a zero-tolerance policy for silent or unhandled failures. The system's new baseline is to be explicitly self-correcting and to fail loudly and predictably when it cannot.
2.  **Pillar 2: Explicit State as a Control Plane.** The Dossier and Ranked Fallback Routing patterns represent a fundamental shift. We are moving away from relying on LLM inference for control flow and towards using structured data *within the state* (`dossier`, `routing_plan`) to direct the system deterministically. This is the tactical foundation for the "Declarative Guardrails" envisioned in Bedrock.
3.  **Pillar 3: The Hybrid Routing Engine.** The combination of Reflexive Routing (procedural), Ranked Fallback (planned), and the traditional LLM call (probabilistic) has created a new, de facto multi-stage routing architecture. The next roadmap should formalize this hybrid engine and expand its capabilities.
4.  **Pillar 4: Professionalized Platform & Tooling.** The decisions around containerization and the decomposition of the archiver into composable file tools signal a maturation of the project. The system is evolving from a monolithic agent into a platform of reusable services and capabilities.