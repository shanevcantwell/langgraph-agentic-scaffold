# ADR-TS-002: Multi-Layered Integration Testing Strategy

**Status:** Completed **Date:** 2025-10-01

## Context

The existing test suite, while benefiting from the fixture-based unit testing improvements of `ADR-TS-001`, lacks a comprehensive strategy for integration testing. The current "integration tests" are limited to verifying the contract between LLM adapters and live external APIs. They do not validate the critical interactions *between* internal components or the full, end-to-end application lifecycle.

As the system's architecture grows in complexity with the introduction of new contracts and behaviors (e.g., the "Atomic Archival Package" defined in `ADR-OBS-001`), this gap in testing becomes an unacceptable risk. Without automated, reliable integration tests, we cannot ensure that components collaborate correctly, prevent regressions, or refactor with confidence.

A formal, multi-layered strategy is required to provide robust test coverage that balances fidelity, speed, and cost.

## Decision

We will adopt a **Multi-Layered Integration Testing Strategy** to validate the system at increasing levels of integration. This approach allows for fast, deterministic feedback during development while still providing high-confidence checks against live systems when needed.

### Layer 1: Component Interaction Tests (Internal Integration)

- **Objective:** To verify the data contracts and control flow between collaborating specialists *within* the graph, without the non-determinism or cost of live LLM calls.  
- **Architecture:** These tests will live in `app/tests/integration/`. They will use `pytest` fixtures to instantiate multiple specialists. The specialists' `llm_adapter` attributes will be `MagicMock` objects, configured to return predictable, canned responses. The tests will simulate the flow of `GraphState` between these components.  
- **Example:** A test will verify that when a mock `RouterSpecialist` routes to the `FileSpecialist`, the `FileSpecialist` is invoked with the correct state and its tool-call schema is correctly interpreted.

### Layer 2: Full Workflow Tests (End-to-End with Mocked Externals)

- **Objective:** To test the entire application stack, from the API endpoint through graph execution to the final archival output, in a fully controlled and deterministic environment. This is the most critical layer for validating architectural contracts.  
- **Architecture:** These tests will use a FastAPI `TestClient` to make requests to the application's API. The `AdapterFactory` will be patched to produce adapters that connect to a **mock LLM API server** (e.g., using `pytest-httpserver`). This mock server will be programmed with specific request/response sequences to drive a predictable workflow.  
- **Example:** A test will send a prompt to the `/invoke` endpoint and configure the mock server to guide the agent through a multi-step task. The test will then assert the contents of the final `.zip` archive.

### Layer 3: Live End-to-End "Smoke" Tests

- **Objective:** To provide a final sanity check that the system can successfully interact with live, external LLM providers. These tests are not for complex logic but for catching breaking API changes.  
- **Architecture:** These tests will be minimal in number and marked with `@pytest.mark.live_e2e`. They will run the full, unmodified application stack against live APIs, using simple, predictable "golden path" prompts. They should be run sparingly (e.g., nightly or pre-release) due to their non-determinism, cost, and long execution time.

### Validation of Architectural Contracts

A primary purpose of this testing strategy is to provide automated enforcement of the system's architectural contracts. The Layer 2 tests are specifically responsible for this.

**The integration test suite MUST include assertions that validate the "Atomic Archival Package" contract as defined in `ADR-OBS-001`.** This includes, but is not limited to:

1. Asserting that a single `.zip` file is the final output.  
2. Unzipping the archive in-memory or to a temporary directory.  
3. Asserting the existence and structural integrity of the `_archive_report.md` manifest.  
4. Asserting the existence of all expected artifacts and assets in their native formats.  
5. Validating the referential integrity of assets (e.g., parsing an HTML artifact and confirming its `<img>` `src` attribute matches an asset filename in the archive).

### Initial Implementation Plan

To provide immediate value, we will prioritize the implementation of Layer 2 tests for the following high-value workflows:

1. **Simple Generation Workflow:** A basic, single-step task that validates the core "happy path" from prompt to archive, including the mandatory termination sequence.  
2. **"Plan and Execute" Tool Use Workflow:** A multi-step task that requires the use of a tool-enabled specialist (e.g., `FileSpecialist`), validating the tool-use and orchestration logic.  
3. **"Generate-and-Critique" Loop Workflow:** A stateful, multi-turn workflow that validates the system's ability to handle controlled loops and iterative refinement.

## Consequences

### Positive

- **High Confidence:** Provides robust, end-to-end validation of the system's behavior.  
- **Regression Prevention:** Automated tests will catch breaking changes before they are merged.  
- **Enforced Architecture:** The system's core contracts (e.g., archival format) are automatically verified on every run, preventing architectural drift.  
- **Improved Developer Experience:** Enables safe refactoring and provides fast, deterministic feedback (via Layer 1 & 2 tests) for most development tasks.

### Negative

- **Increased Development Overhead:** Setting up the test harnesses, particularly the mock API server for Layer 2 tests, requires a significant initial investment of time and effort.  
- **Test Maintenance:** As the application evolves, the integration tests must be maintained, which requires ongoing developer discipline.  
- **CI Complexity:** CI workflows will need to be configured to distinguish between fast (Layer 1/2) and slow (Layer 3\) tests to maintain efficient feedback loops.

