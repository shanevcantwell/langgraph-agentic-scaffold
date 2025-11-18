# Project Bedrock v4.0 Roadmap

## Workstream 1: Foundational Resilience & Stability
- [x] **Task 1.4: Define System Invariants**
  - Define `Invariant` abstract base class.
  - Implement `MaxTurnsInvariant` (limit graph steps).
  - Implement `LoopDetectionInvariant` (prevent repetitive state).
  - Implement `StateStructureInvariant` (validate Pydantic schema).
- [x] **Task 1.5: Implement InvariantMonitor Service**
  - Create `InvariantMonitor` class.
  - Integrate into `GraphOrchestrator`.
  - Add LangSmith `@traceable` for observability.
- [x] **Task 1.6: Configure Circuit Breaker Actions**
  - Define action types (HALT, RETRY, HUMAN_INTERVENTION).
  - Implement mapping from `InvariantViolationError` to actions.
  - Update configuration schema to support stabilization actions.

## Workstream 2: Observability & Debugging (Inferred)
- [ ] **Task 2.1: Enhanced Logging**
- [ ] **Task 2.2: LangSmith Integration Deep Dive**

## Workstream 3: Hybrid Routing (Scatter-Gather)
- [x] **Task 3.1: Define Router Interface**
  - Update `RouterSpecialist` to support list-based output.
  - Update `GraphOrchestrator` to handle parallel routing validation.
  - Update `router_prompt.md` with scatter-gather instructions.
- [ ] **Task 3.2: Implement Parallel Execution**
- [ ] **Task 3.3: Result Aggregation**

## Workstream 4: Specialist Agents
- [ ] **Task 4.1: Refactor Existing Agents**
- [ ] **Task 4.2: Create New Specialist Templates**
