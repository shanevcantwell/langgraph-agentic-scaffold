

# **Project Bedrock v3: A Roadmap for a Resilient, Modular, and Interoperable Reasoning Architecture**

## **Executive Summary**

This document outlines the third evolution of the Project Bedrock roadmap. Building upon the foundation of architectural decomposition (v1) and the integration of advanced resilience patterns like Guardrails and Context Engineering (v2), this revision focuses on enhancing system modularity, communication flexibility, and standardized interoperability.

Architectural review has highlighted the necessity of formalizing how specialists interact internally and how the system presents its state externally. This roadmap integrates two critical architectural patterns to address these needs:

1. **Multi-Layered Communication (Dossier and MCP):** Formalizing the distinction between asynchronous workflow orchestration (via the Dossier pattern) and synchronous, direct tool invocation (via the Message-Centric Protocol/Microservice Communication Pattern, MCP). This enhances modularity by enabling specialists to interact as decoupled microservices where appropriate.  
2. **Standardized Presentation Layer (AG-UI):** Adopting the AG-UI standard for event streaming. This cleanly decouples the front-end presentation layer from the back-end execution logic, leveraging our existing event-driven architecture to enhance observability and interoperability.1

This roadmap synthesizes these initiatives into a prioritized, incremental plan, ensuring our architecture remains robust, scalable, and prepared for future microservices-style deployment.

---

## **Phase 1: Architectural Decomposition (The Great Divide)**

**Status:** Complete

**🎯 Goal:** Decompose the monolithic ChiefOfStaff into distinct build-time (GraphBuilder) and run-time (GraphOrchestrator) components.

**💡 Architectural Rationale:** The decomposition of the monolith was a critical prerequisite, establishing a clean separation of concerns necessary for implementing the advanced orchestration and communication patterns in subsequent phases.

### **📝 Task Checklist**

* \[x\] Decomposed ChiefOfStaff into GraphBuilder and GraphOrchestrator.  
* \[x\] Migrated build-time and run-time logic successfully.  
* \[x\] Verified functional equivalence and system stability.

---

## **Phase 2 (Evolved): The Multi-Layered Communication Architecture (Dossier & MCP)**

**Status:** In Progress

**🎯 Goal:** Define and implement a multi-layered communication architecture, utilizing the **Dossier** pattern for asynchronous workflow orchestration and **MCP** for synchronous inter-specialist tool invocation.

**💡 Architectural Rationale:** We must resolve inconsistent state management and define precise communication protocols before introducing advanced logic. A robust architecture requires different communication strategies for different needs:

* **Dossier (Asynchronous Orchestration):** Ideal for passing control flow and large data payloads *between steps* in the main, stateful workflow. It ensures the GraphState remains the single source of truth and the process is traceable (e.g., in LangSmith).  
* **MCP (Synchronous Invocation):** Ideal when one specialist needs a discrete service or data lookup from another (acting as a tool) *without ceding control* of the workflow. This promotes decoupling and modularity, treating specialists as microservices.

### **📝 Task Checklist**

#### **2.1. Implement the Dossier Pattern (State-Mediated Orchestration)**

* \[ \] Define the Dossier TypedDict schema in app/src/graph/state.py (including recipient, payload\_key, message).  
* \[ \] Update GraphState to include dossier: Optional\[Dossier\].  
* \[ \] Modify the GraphOrchestrator to prioritize and deterministically route based on the dossier.  
* \[ \] Ensure the orchestrator consumes the dossier after routing to prevent reprocessing.

#### **2.2. Implement the MCP Pattern (Direct Tool Invocation)**

* \[ \] **Define the MCP Interface:** Define standardized Pydantic schemas for MCP requests and responses. This establishes the API contract for internal tool calls.  
* \[ \] **Implement an MCP Client:** Create a utility client library (McpClient) that specialists can use to make synchronous calls to MCP services.  
* \[ \] **Refactor a Specialist as an MCP Service:** Expose the functions of a simple, stateless specialist (e.g., the Librarian/file\_specialist) via a simple MCP-compliant API endpoint.

#### **2.3. System-Wide Refactoring and State Cleanup**

* \[ \] **CRITICAL (Breaking Change):** Remove all deprecated, specialist-specific fields from GraphState (e.g., text\_to\_process).  
* \[ \] Audit all specialists (app/src/specialists/\*.py).  
* \[ \] **Apply Dossier:** For interactions representing a handoff of control in the main workflow (e.g., web\_builder to critic), refactor them to use the Dossier pattern (writing payloads to artifacts and addressing the Dossier).  
* \[ \] **Apply MCP:** For interactions representing a simple data lookup or service call within a specialist's execution turn (e.g., TriageArchitect calling Librarian's file\_exists), refactor them to use the MCP client.

---

## **Phase 3 (New): Standardized Presentation Layer (AG-UI Integration)**

**Status:** Planned

**🎯 Goal:** Implement the AG-UI standard to decouple the presentation layer from the core agentic workflow, exposing a standardized, real-time event stream for observability.

**💡 Architectural Rationale:** Our LangGraph architecture is inherently event-driven. Adopting the AG-UI standard allows us to translate internal events into a standardized format. This is a non-invasive, high-value addition ("low-hanging fruit") that significantly improves interoperability and cleanly decouples front-end development from back-end architecture without requiring any refactoring of the specialists or the GraphOrchestrator.

### **📝 Task Checklist**

#### **3.1. Define the Translation Layer**

* \[ \] Define the mapping between internal LangGraph events (e.g., node start, node end, state update, artifact creation) and the standardized AG-UI event schema (on\_run\_start, on\_tool\_start, on\_artifact\_create, on\_run\_end, etc.).

#### **3.2. Implement the Emitter Middleware**

* \[ \] Create a new middleware component, the AgUiEmitter, initialized within the WorkflowRunner.  
* \[ \] Configure the AgUiEmitter to subscribe to the LangGraph execution stream.  
* \[ \] Implement the logic within the emitter to translate internal events into the AG-UI format in real-time.

#### **3.3. Expose the Standardized Stream**

* \[ \] Update the WorkflowRunner API to expose this translated stream via an appropriate endpoint (e.g., using Server-Sent Events (SSE) or WebSockets).

---

## **Phase 4 (Shifted): Declarative Guardrails & Routing Engine (The Policy Proxy)**

*(Previously Phase 3\)*

**Status:** Planned

**🎯 Goal:** Evolve the GraphOrchestrator into a declarative, rule-based routing engine, utilizing the Guardrails-as-Proxy pattern. The RouterSpecialist is repositioned as an escalation path, not the default decision-maker.

**💡 Architectural Rationale:** Relying on an LLM (RouterSpecialist) for every decision is costly, slow, and prone to non-deterministic errors. By implementing a Declarative Guardrails system, we enforce policies and handle known states deterministically *before* invoking the LLM. This increases resilience and efficiency. This phase relies on the clean communication established in Phase 2\.

### **📝 Task Checklist**

#### **4.1. Define the Guardrail Schema**

* \[ \] Update config.yaml standards to support a guardrails section with declarative rules based on state signals (e.g., on\_event: "last\_execution\_status \== 'FAILURE'").

#### **4.2. Emit Structured Execution Signals**

* \[ \] Modify the GraphOrchestrator's safe\_executor wrapper to emit structured, machine-readable signals into the scratchpad upon specialist success or failure.

#### **4.3. Implement the Rule Engine (GraphOrchestrator Refactor)**

* \[ \] Refactor the GraphOrchestrator's decider functions to act as a rule engine.  
* \[ \] Implement logic to evaluate the current GraphState against the configured guardrails and enforce matching rules deterministically.

#### **4.4. Reposition the RouterSpecialist**

* \[ \] Configure the decider functions to invoke the RouterSpecialist ONLY if no deterministic guardrail rule is matched (the escalation path for ambiguous states).

---

## **Phase 5 (Shifted): The Context Engineering Ecosystem (The Meta-Agent Subgraph)**

*(Previously Phase 4\)*

**Status:** Planned

**🎯 Goal:** Implement a meta-agentic subgraph responsible for dynamically acquiring, refining, and assembling the optimal context payload for "Solver" agents.

**💡 Architectural Rationale:** The capability of our primary "Solver" agents is fundamentally limited by the quality of their input context. We must treat context as a dynamic, just-in-time engineered artifact. This ecosystem ensures the Solver receives the most relevant, compressed, and accurate information, improving output quality and optimizing token utilization. This ecosystem will leverage the hybrid communication architecture (Dossier for orchestration and MCP for synchronous data lookups) established in Phase 2\.

### **5.1. Ecosystem Components**

| Component | Role | Primary Function | Model Type |
| :---- | :---- | :---- | :---- |
| **Triage Architect** | The Planner | Creates a "context acquisition plan." | Small, Fast (Tool/Function Calling) |
| **Librarian** | The Archivist | Retrieves structured information from a local knowledge base. | Procedural (Code/MCP Service) |
| **Researcher** | The Scout | Fetches unstructured, real-time information from external sources. | Procedural (API Call/MCP Service) |
| **Summarizer** | The Distiller | Performs semantic compression on large text artifacts. | Medium, Fast (Summarization-tuned) |

### **5.2. Workflow Diagram (Hybrid Communication Model)**

Code snippet

graph TD  
    subgraph "User Interaction"  
        A\[User Prompt\]  
    end  
    subgraph "Context Engineering Ecosystem (The Meta-Agent)"  
        B(Triage Architect)  
        C(Facilitator/Orchestrator)  
        D(Librarian)  
        E(Researcher)  
        G(Summarizer)  
    end  
    subgraph "Solver Agent (The Primary Agent)"  
        H{Solver Agent}  
    end  
    A \--\> B;  
    B \-- MCP Call (e.g. file\_exists?) \--\> D;  
    B \-- Context Plan (Dossier) \--\> C;  
    C \-- Invokes (MCP/Direct) \--\> D & E & G;  
    D \-- Data \--\> C;  
    E \-- Data \--\> C;  
    G \-- Data \--\> C;  
    C \-- Assembled Context (Dossier) \--\> H;  
    H \-- Final Response \--\> A;

### **📝 Task Checklist**

#### **5.3. Introduce New Specialist Roles**

* \[ \] Implement the TriageArchitect to generate a structured "context acquisition plan." (Note: Triage will use the MCP Client to consult specialists like the Librarian synchronously during planning).  
* \[ \] Ensure the Librarian (refactored in Phase 2\) is ready for targeted local data retrieval via both Dossier and MCP.  
* \[ \] Implement the Researcher for real-time external data retrieval.  
* \[ \] Implement the Summarizer for semantic compression.

#### **5.4. Develop the Facilitator**

* \[ \] Implement the Facilitator logic to interpret and execute the TriageArchitect's plan.  
* \[ \] The Facilitator orchestrates the context specialists (using MCP or direct calls for data retrieval) and assembles the final context payload for the target Solver agent (using the Dossier pattern for handoff).

#### **5.5. Integrate into Main Graph**

* \[ \] Update the GraphBuilder to wire this ecosystem into the main execution graph as a preliminary phase before "Solver" specialists are invoked.

---

## **Phase 6 (Shifted): System-Wide Invariant Monitoring (The Circuit Breaker)**

*(Previously Phase 5\)*

**Status:** Planned

**🎯 Goal:** Harden the system against unexpected states and ensure overall stability through a system-wide invariant monitoring mechanism.

**💡 Architectural Rationale:** This is the capstone of the architecture. With the implementation of complex communication protocols (Phase 2), declarative routing (Phase 4), and the dynamic Context Engineering workflow (Phase 5), the potential state space of the system has increased significantly. A system-wide "circuit breaker" is critical to detect and prevent unforeseen pathological states (e.g., infinite loops, deadlocks, state corruption) and ensure long-term resilience.2

### **📝 Task Checklist**

#### **6.1. Define System Invariants**

* \[ \] Define critical system-wide invariants (e.g., Maximum overall execution time, maximum consecutive errors, strict adherence to GraphState schema).

#### **6.2. Implement the InvariantMonitor Service**

* \[ \] Implement the InvariantMonitor service, integrated deeply within the GraphOrchestrator's main execution loop.  
* \[ \] The monitor must check invariants before and after every node execution.

#### **6.3. Configure "Circuit Breaker" Actions**

* \[ \] Define a schema for stabilization actions in config.yaml.  
* \[ \] Implement logic to trigger actions when an invariant is violated (e.g., Halting execution gracefully, forcing a route to HumanIntervention, logging a critical system error).