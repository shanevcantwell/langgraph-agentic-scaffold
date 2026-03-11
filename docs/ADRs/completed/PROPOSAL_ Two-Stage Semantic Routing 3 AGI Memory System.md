# **Two-Stage Semantic Routing: AGI Memory System**

#### **By Shane V Cantwell and Gemini 2.5 Pro Deep Think** **August 23, 2025**

This is a deep-dive architectural analysis of how the proposed AGI Memory System integrates with and fundamentally enhances the agentic routing architecture, particularly the Unified Hierarchical Reasoning Model (HRM) Planner.

The integration of this sophisticated, multi-modal memory system is the critical evolutionary step required to maximize first-try accuracy. The HRM Planner provides the computational depth for reasoning, but it requires a rich, accurate representation of the world state, historical context, and available actions. The AGI Memory System provides this foundation, transforming the architecture from a reactive sequencer into a learning, context-aware strategist.

See also: [https://github.com/QuixiAI/agi-memory](https://github.com/QuixiAI/agi-memory) 

### **The Core Principle: Memory as the State Substrate**

The fundamental principle of this integration is that **Memory *is* the State**. Accurate routing requires transitioning from stateless classification to stateful, experience-driven planning. The AGI Memory System serves as the substrate of the agent's cognition, providing the data required for the HRM to reason effectively.

### **Architectural Integration: The Cognitive Nexus**

The integration hinges on two key components: the **ChiefOfStaff (CoS)** acting as the memory mediator, and the **State and Action Encoder** within the HRM Planner architecture.

#### **1\. The ChiefOfStaff as Memory Mediator**

The CoS manages the interaction between the execution environment, the memory system, and the planning agents.

* **The Write Path (Continuous Logging):** The CoS logs every action in real-time. Initial prompts and intents are loaded into **Working Memory (WM)**. Every specialist invocation (input, output, outcome, cost, duration) is logged for later consolidation into **Episodic Memory (EM)**. Telemetry data (success rates, failure points) updates **Procedural Memory (PM)**.  
* **The Read Path (Contextualized Retrieval):** Before invoking the HRM Planner, the CoS proactively queries the memory system to prepare the cognitive state. It synthesizes relevant history (EM), known procedures (PM), and active strategies (Strategic Memory \- STM) relevant to the current goal.

#### **2\. The Memory-Augmented State and Action Encoder**

This component is the crucial bridge between the diverse data modalities of the Memory System (relational, vector, graph) and the unified tensor input required by the HRM Core. It synthesizes the vast knowledge stored in the memory system into a compressed, actionable "State and Action Space Tensor."

### **The Role of Memory Types in Enhancing Planning Depth**

Each memory type plays a distinct role in constructing the tensors used by the HRM Core, directly contributing to planning accuracy.

#### **A. Working Memory (WM): The Immediate Context**

* **Function:** Holds the transient state of the current execution run—the "scratchpad."  
* **Integration:** The Encoder pulls the active artifacts, the immediate goal, and active constraints from WM. This defines the "starting state" of the planning problem, ensuring the HRM Core is grounded in the immediate reality.

#### **B. Semantic Memory (SM): The Knowledge Graph of Capabilities**

* **Function:** Stores formalized facts about the system's capabilities—the I/OPE signatures (Inputs, Outputs, Preconditions, Effects), QoS profiles, and learned constraints. This replaces the static config.yaml.  
* **Integration:** Utilizing the graph capabilities (Apache AGE), the Encoder understands the "Action Space." By modeling capabilities as a graph (Nodes=States/Artifacts, Edges=Specialists), the Encoder can perform complex dependency analysis (e.g., traversing the graph to find the shortest path from the current state to the goal state).

#### **C. Episodic Memory (EM): The Engine of Improvement (Case-Based Reasoning)**

* **Function:** Logs the history of execution runs, including successes, failures, and emotional valence (risk/reward signals).  
* **Integration:** The Encoder performs a vector similarity search (using pgvector) against EM, using the Goal Tensor as the query vector. This enables **Case-Based Reasoning**. If a highly similar past episode is found, the successful plan can be prioritized in the HRM's simulation. Conversely, memories of past failures serve as critical counter-examples, enabling proactive failure avoidance.

#### **D. Procedural Memory (PM): Pre-compiled Sub-Plans (SOPs)**

* **Function:** Stores validated, multi-step sequences (Standard Operating Procedures) that reliably achieve common sub-goals.  
* **Integration:** Provides hierarchical abstraction. The HRM Planner can treat a stored procedure as a single "macro-action" rather than sequencing individual specialists, significantly reducing the complexity of the search space.

#### **E. Strategic Memory (STM): The High-Level Playbook**

* **Function:** Stores high-level patterns and adaptation history about which strategies are optimal in different contexts.  
* **Integration:** Informs the high-level (slower, abstract) module of the HRM. This allows the HRM to select an overarching strategy (e.g., "minimize cost" or "maximize speed") before committing to tactical steps.

### **The Continuous Learning Loop**

The memory system is not just for storage; it is the engine for continuous improvement and the mechanism for training the HRM Planner.

1. **Memory Consolidation:** The offline process of consolidating data from WM to EM/PM/SM is critical. This process analyzes execution paths and outcomes.  
2. **Optimization and Abstraction:** Successful runs are optimized and abstracted into new entries in PM and STM. Failures trigger analysis, potentially creating new constraints in SM.  
3. **Training Data Generation:** These consolidated, optimized paths serve as the high-quality training data ((Goal, State) \-\> \[Optimal Sequence\]) required to train the HRM Planner. This feedback loop ensures the HRM continuously adapts to new tasks and changes in the toolset.

### **Implementation Challenges and Solutions**

Integrating these systems introduces complexity that must be managed.

#### **1\. The Encoding Bottleneck: Graphs to Tensors**

The most significant challenge is encoding the rich, multi-modal memory structure—particularly the graph relationships (AGE)—into the fixed-size tensor format required by the HRM Core.

* **Solution: Graph Neural Networks (GNNs).** The State and Action Encoder must incorporate a GNN layer. The GNN processes the graph structure of the specialists and their dependencies (from SM), generating embeddings that capture the relational structure of the action space. These embeddings are then combined with the state information from WM to form the final input tensor.

#### **2\. Latency Management**

Querying multiple database types (relational, vector, graph) during the planning phase introduces latency.

* **Solution: Optimized Indexing and Caching.** The system must leverage the PostgreSQL extensions effectively. Furthermore, Semantic and Procedural memories change relatively slowly. The Encoder should maintain an aggressively updated in-memory cache of I/OPE signatures and SOPs to avoid database latency during the critical planning phase.

### **The Synthesized Cognitive Architecture**

The integration results in a robust, self-improving Cognitive Control Loop:

\`\`\` Code snippet  
graph TD  
    User\[User Prompt\] \--\> NLU\[NLU Interpreter\]  
    NLU \--\>|Goal Tensor| WM\[Working Memory\]

    subgraph Memory System DB (Postgres+Vector+Graph)  
        WM  
        EM\[Episodic Memory\]  
        SM\[Semantic Memory\]  
        PM\[Procedural Memory\]  
        STM\[Strategic Memory\]  
    end

    COS\[ChiefOfStaff\] \<--\>|Mediation (Log/Retrieve)| Memory System DB

    %% The Encoder Bridge  
    subgraph Encoder \[State & Action Encoder\]  
        direction LR  
        GNN\[GNN Layer\]  
        Cache\[In-Memory Cache: SM/PM\]  
        Tensorizer\[Tensor Compiler\]  
    end

    WM \--\> Encoder  
    EM \--\>|Vector Search: History| Encoder  
    SM \-- Graph Data \--\> GNN  
    GNN \--\> Tensorizer  
    STM \--\> Encoder

    %% The Planner  
    Encoder \--\>|State & Action Tensor| HRM\[HRM Core Planner\]

    HRM \--\>|Execution Plan| Executor\[Execution Module\]  
    Executor \--\> Specialists\[Specialists/Tools\]  
    Specialists \--\>|Outcomes| COS

    %% Learning Loop  
    Memory System DB \-.-\>|Consolidation (Training Data Gen)| HRM  
\`\`\`