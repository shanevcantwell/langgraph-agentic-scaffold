## **Refactor ChiefOfStaff into GraphBuilder and GraphOrchestrator**

**Status:** Proposed

---

### **Context**

The ChiefOfStaff class has evolved into a central monolith for the application's workflow. While functional, it has accumulated a wide range of responsibilities, making it difficult to maintain, test, and reason about. This violates the **Single Responsibility Principle (SRP)** and goes against our preferred architectural style of having a broad number of shallow-length code files.

Currently, the ChiefOfStaff performs two distinct and unrelated jobs:

1. **Build-Time Factory:** At application startup, it loads configuration, instantiates specialists, and assembles the StateGraph object.  
2. **Run-Time Logic:** During a workflow's execution, the compiled graph calls back to methods within the ChiefOfStaff instance (e.g., decide\_next\_specialist, safe\_executor) to make live decisions.

This conflation of a "builder" with the "runtime engine" creates tight coupling and makes the system's architecture opaque.

---

### **Decision**

We will eliminate the ChiefOfStaff class and refactor its responsibilities into two new, single-purpose classes: a **GraphBuilder** and a **GraphOrchestrator**.

1. **The GraphBuilder Class:**  
   * **Responsibility:** To be solely responsible for the **one-time setup and compilation** of the graph at application startup. This includes loading configs, instantiating all specialists and their dependencies (e.g., adapters), adding nodes, and wiring the graph edges.  
   * **Lifecycle:** This class will be **ephemeral**. The WorkflowRunner will instantiate it at startup, call a .build() method to receive the final compiled graph, and then the GraphBuilder instance will be discarded.  
2. **The GraphOrchestrator Class:**  
   * **Responsibility:** To contain all the **live, runtime logic** that is executed by the compiled graph. This includes the decide\_next\_specialist routing logic, the after\_synthesis\_decider termination logic, and the safe\_executor wrapper for specialist calls.  
   * **Lifecycle:** An instance of this class will be created by the GraphBuilder. Its methods will be passed into the StateGraph during compilation, effectively "baking" the orchestration logic into the final, persistent graph object.

---

### **Consequences**

#### **Positive**

* **Adherence to SRP:** Each new class will have a single, clearly defined responsibility, dramatically improving the clarity of the architecture.  
* **Improved Maintainability:** Developers will know exactly where to go to modify either the graph's structure (GraphBuilder) or its runtime behavior (GraphOrchestrator).  
* **Enhanced Testability:** The build process and the runtime logic can be unit-tested in complete isolation, leading to simpler and more reliable tests.  
* **Reduced Cognitive Load:** This change aligns with our goal of having more, smaller, and shallower files, which are easier to understand, manage, and process as context for LLMs.  
* **Decoupling:** It eliminates the confusing pattern of the builder injecting its own methods into the product it is building.

#### **Negative**

* **Increased File Count:** This refactor will increase the number of classes and files in the workflow directory. This is a deliberate and accepted trade-off for the significant gains in clarity, testability, and long-term maintainability.