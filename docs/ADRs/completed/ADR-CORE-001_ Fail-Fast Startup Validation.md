## ADR-010: Fail-Fast Startup Validation for Critical Specialists

**Status:** Completed

---

### Context

The current application architecture allows for "soft failures" during the specialist loading sequence at startup. The `ChiefOfStaff` is designed to be resilient, logging an error if a specialist fails to load (e.g., due to a missing dependency, misconfiguration, or import error) and then continuing the startup process with the remaining specialists.

While this resilience is useful for non-essential components, it has led to significant debugging challenges. A recent persistent `ValueError` during graph compilation was traced back to the **`archiver_specialist`** failing to load silently. The actual root cause (an `ImportError`) was only available in `DEBUG`-level logs and was masked by the loud, but misleading, downstream compilation error. This makes the system fragile and the developer experience frustrating, as the true point of failure is obscured.

---

### Decision

We will implement a **fail-fast startup validation mechanism** to ensure the integrity of the application's core components. This will be achieved by introducing a configurable pre-flight check for "critical" specialists.

1.  **Configuration:** A new optional list, `critical_specialists`, will be added to the `workflow` section of `config.yaml`. This list will contain the string names of specialists considered essential for the application to function correctly.

2.  **Validation Logic:** During the startup sequence, after the initial attempt to load all specialists, the `ChiefOfStaff` or `WorkflowRunner` will perform a new validation step.

3.  **Enforcement:** This validation logic will compare the list of successfully loaded specialists against the `critical_specialists` list from the configuration. If any specialist designated as critical is not found among the successfully loaded ones, the application will **raise an explicit `ConfigError`** and immediately terminate the startup process. The error message will clearly state which critical specialist(s) failed to load.

---

### Consequences

#### Positive

* **Improved Debuggability:** Transforms silent, difficult-to-diagnose runtime errors into loud, clear, and immediate startup failures. The root cause of a critical component failure will become obvious.
* **Increased Robustness:** Prevents the application from starting in a partially-functional, broken state where core capabilities are unexpectedly missing.
* **Explicit Dependencies:** The system's core dependencies become explicit and declarative in the configuration, rather than being implicit in the graph's wiring logic.
* **Enhanced Extensibility:** Developers forking this scaffold can easily define and enforce their own set of essential specialists for their specific use case without modifying the core application code.
* **Codified Architecture:** This provides a concrete mechanism for programmatically enforcing documented architectural patterns, such as ensuring all components of the **Three-Stage Termination Pattern** are present if that pattern is in use.

#### Negative

* **Reduced Flexibility (Minor):** Developers may need to comment out specialists from the `critical_specialists` list during certain testing scenarios if they intentionally want to run the application without a core component. This is a minor trade-off for the significant gain in stability.