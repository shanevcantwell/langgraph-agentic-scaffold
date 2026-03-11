# **Two-Stage Semantic Routing** 

#### **by Shane V Cantwell and Gemini 2.5 Pro Deep Think** **August 23, 2025**

This is a deep, critical analysis of the proposed "Two-Stage Semantic Routing" architecture, with novel suggestions aimed at maximizing first-try accuracy.

The "Two-Stage Semantic Routing" design provides a solid foundation, particularly the dynamic runtime awareness managed by the ChiefOfStaff. However, relying on two sequential LLM calls based purely on semantic descriptions introduces brittleness and compounds the probability of error.

To achieve maximum first-try accuracy, the architecture must evolve from reactive semantic matching to proactive, context-aware, and predictive planning.

### 

### **1. Enhancing Triage: Beyond Semantic Matching**

The PromptTriageSpecialist must move beyond surface-level descriptions to understand the deep structure of specialist capabilities and the user's latent intent.

A. Formalized Capability Signatures (I/OPE Model):  
We must replace ambiguous description strings with structured capability signatures. The I/OPE model (Inputs, Outputs, Preconditions, Effects) provides a robust framework:

* **Inputs/Outputs:** Define the data schemas or artifact types a specialist consumes and produces.  
* **Preconditions:** The state requirements that must be met before execution (e.g., "user authenticated," "file exists").  
* **Effects:** The guaranteed changes to the system state after successful execution.

Triage should transition from semantic similarity to constraint satisfaction, identifying specialists that bridge the gap between the current state (Preconditions met) and the desired state (Outputs/Effects needed).

B. Dynamic Context Injection and State Awareness:  
The meaning of a prompt (e.g., "Analyze that data") depends entirely on context. The ChiefOfStaff must inject the current system state—including execution history, available artifacts, and recent errors—into the Triage prompt.  
C. Historical Execution Telemetry (The "Digital Twin"):  
Triage should leverage past performance data. Maintain a log of (Prompt, State, Specialist, Success/Failure, Duration). This data can train a predictive model (a "digital twin" of the execution environment) that Triage consults to obtain a "probability of success" score for each specialist given the current context.  
D. Intent and Constraint Modeling:  
Triage should not just classify the task but also extract constraints (e.g., "must be fast," "must use Python 3.10"). This richer intent model allows for precise filtering of specialists who cannot meet the non-functional requirements.

### **2. Enhancing the Router: Reasoning about Dependencies and Sequencing**

The RouterSpecialist must evolve from a tactical selector into a strategic planner capable of handling novel problems.

A. Dynamic Dependency Inference via I/OPE:  
For novel problems without explicit dependencies, the Router must analyze the I/OPE signatures. If the Preconditions of a target specialist are not met by the current state, the Router must dynamically insert a preceding specialist whose Effects satisfy those Preconditions.  
B. Lightweight Lookahead Simulation:  
When faced with ambiguity, the Router should perform a shallow (1-2 step) lookahead. It should ask: "If I choose Specialist A, what is the likely new state, and what specialists will be needed next?" It then evaluates the desirability of these future states, preventing locally optimal decisions that lead to dead ends.  
C. Chain-of-Thought (CoT) for Tactical Justification:  
Explicitly prompt the Router to use CoT reasoning focused on state requirements and risk. The Router must articulate why a path is chosen, verifying Preconditions and anticipating Effects.  
D. Implicit Dependency Learning (RLAIF):  
The system must learn from experience. Implement Reinforcement Learning from AI Feedback (RLAIF) to fine-tune the Router. The reward function should prioritize efficient (fewer steps) and successful outcomes. This allows the Router to learn implicit dependencies and optimal sequencing strategies that are too complex to define declaratively.

### **3. Alternative & Hybrid Models: The "Hydra" Architecture**

The sequential "Triage-then-Route" model is suboptimal as an error in Triage guarantees a subsequent routing error.

A. The Adaptive Hybrid Model (Confidence Gating):  
Maintain the fast Two-Stage model for simple requests. If Triage returns a single specialist with very high confidence (>95%), bypass the Router and execute directly. If confidence is lower or the task complexity is high, escalate to a more robust model.  
B. Parallel "Outcome-Based" Simulation (The "Hydra" Router):  
For complex or ambiguous cases, this model maximizes first-try accuracy:

1. **Hypothesis Generation:** Triage identifies the top 3-5 potential first steps.  
2. **Parallel Simulation:** The "Hydra" Router dispatches the request to these candidates in parallel, invoking a standardized simulate() method rather than execute().  
3. **Evaluation:** Specialists return a (proposed_plan, predicted_success_score, estimated_cost).  
4. **Selection:** The Router evaluates these concrete proposals and authorizes execution of the optimal path.

C. Blackboard Architecture (Opportunistic Routing):  
For systems with highly diverse toolsets, consider a Blackboard model. Specialists monitor a shared memory space (the blackboard). When a specialist recognizes an artifact it can act upon, it "bids" to be the next step. The Router acts as an arbitrator, selecting the bid that best advances the goal. This fosters emergent, opportunistic behavior.

### **4. Richer Configuration: Actionable Understanding**

The config.yaml must provide actionable insights without violating DRY principles, supporting the advanced techniques above.

* **I/OPE Signatures:** The most critical addition (detailed in Section 1).  
* **Quality of Service (QoS) Profile:** Replace simple cost/priority with structured metrics: estimated_latency_class (e.g., "instant", "slow", "blocking"), reliability_score, and cost_profile (e.g., "high_compute", "api_cost").  
* **Execution Semantics:**  
  * idempotency: Can the specialist be safely rerun?  
  * state_mutation: Does the specialist change the external environment (e.g., mutates_filesystem: true)?  
* **Failure Modes and Anti-Patterns:** Declarative information about *when not* to use a specialist or common conditions under which it fails (e.g., "Requires GPU," "Fails if API rate limit exceeded").

### **5. Factoring in Execution Risk: The tail -f Problem**

The system must proactively manage long-running or blocking tasks during the initial routing decision.

A. Risk-Weighted Utility Calculation:  
The Router should optimize for utility, not just accuracy. It should calculate:  
Utility = (Probability of Success * Value of Outcome) - (Execution Cost + Risk)  
It should often prefer a quick action with moderate success over a slow action with slightly higher success.  
B. Asynchronous Execution Infrastructure:  
The underlying architecture must support asynchronous tasks. Specialists marked as blocking or long_running in the QoS profile should return a "Processing" status immediately, allowing the main agent loop to continue (e.g., via background processes or checkpointing).  
C. Proactive State Checking (Pre-flight Checks):  
Before committing to a high-risk or high-cost specialist, the Router should leverage the failure_modes and Preconditions in the configuration to perform lightweight checks (e.g., checking API availability, validating input schemas).  
D. Proactive Checkpointing:  
If the Router selects a sequence involving a high-risk, state-mutating specialist, it should automatically insert a CheckpointSpecialist immediately before it to ensure the system state is saved, facilitating rapid recovery if the operation fails.