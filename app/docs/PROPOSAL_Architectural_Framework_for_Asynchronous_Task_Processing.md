# PROPOSAL: Architectural Framework for Asynchronous Task Processing
**Version:** 1.0
**Date:** {current_date}
**Status:** DRAFT

## 1.0 Executive Summary

This document proposes an architectural framework for integrating long-running, asynchronous tasks into the SpecialistHub system. The introduction of powerful but time-intensive tools, such as the Veo 3 video generation API, necessitates an evolution beyond our current synchronous request-response model. We will introduce a "Spooler Agent" pattern to manage these tasks without blocking the main application graph, ensuring the system remains responsive and scalable. This proposal outlines two potential implementation patterns and recommends a phased approach for development.

## 2.0 Problem Statement: The Synchronous Bottleneck

The current architecture, where each Specialist's `execute` method runs to completion before returning control, is highly effective for fast, transactional tasks. However, it is fundamentally incompatible with long-running operations (e.g., video generation, large data analysis, batch processing) which can take minutes or hours to complete.

Attempting to run these tasks synchronously would:
*   **Stall the entire graph:** The system would appear frozen and unresponsive.
*   **Lead to API timeouts:** The connection would likely be lost before the task completes.
*   **Provide a poor user experience:** The user would have no feedback or ability to perform other actions.

## 3.0 Proposed Solution: The "Spooler Agent" Pattern

To solve this, we will introduce a new architectural component: a **Spooler Agent** (or "Async Task Processor").

**Analogy:** This component functions like a print spooler. When a user requests a long-running task, the responsible Specialist will not execute the task itself. Instead, it will hand off a "job ticket" to the Spooler system and immediately return control to the main graph. The Spooler then manages the job's lifecycle in the background, freeing the primary conversational agent to remain interactive.

## 4.0 Architectural Implementation Patterns

There are two primary patterns for implementing the Spooler Agent.

### Pattern A: The In-Graph Polling Model

In this model, the Spooler is a passive Specialist node within our existing graph loop.

*   **Workflow:**
    1.  A Specialist (e.g., `VideoSpecialist`) initiates a long-running job and saves its `operation_id` to the `GraphState`.
    2.  The graph loops back to the `Router`.
    3.  The `Router` sees an active `operation_id` and routes to a `PollingSpecialist`.
    4.  The `PollingSpecialist` checks the job status. If incomplete, it does nothing and the loop continues. If complete, it retrieves the result, updates the `GraphState`, and clears the `operation_id`.
    5.  The `Router` now sees the final result and can route to the next logical step (e.g., `NotificationSpecialist`).

*   **Pros:**
    *   Simple to implement as a first version.
    *   Uses our existing LangGraph architecture without external dependencies.
*   **Cons:**
    *   Inefficient "busy-waiting" consumes resources.
    *   High latency in detecting job completion.

### Pattern B: The Asynchronous Worker Model

This is a more robust, decoupled pattern where the Spooler operates as a true background process, outside the main graph.

*   **Workflow:**
    1.  `VideoSpecialist` initiates a job and saves the `operation_id` and a snapshot of the `GraphState` to a persistent queue (e.g., Redis, RabbitMQ).
    2.  The main graph execution ends for the user, providing an immediate "Job started" confirmation.
    3.  A separate, out-of-band **Worker Process** (e.g., a cloud function, a cron job) polls the job status.
    4.  When the Worker finds a completed job, it retrieves the result and its associated `GraphState` from the queue.
    5.  The Worker **initiates a new graph execution**, injecting a new state containing the result, effectively "waking up" the conversation to continue where it left off.

*   **Pros:**
    *   Highly efficient and scalable; the main graph is never blocked.
    *   True decoupling of conversational logic from background processing.
*   **Cons:**
    *   Higher implementation complexity.
    *   Requires additional infrastructure (a message queue, a scheduled worker process).

## 5.0 Strategic Recommendation

A phased approach is recommended to balance immediate capability with long-term architectural health.

1.  **Phase 1 - Implement Pattern A (Polling Model):** This allows us to quickly and pragmatically add support for long-running tasks using our existing framework. It delivers the feature without significant infrastructure overhead.
2.  **Phase 2 - Plan for Pattern B (Worker Model):** While building Phase 1, we will design the `PollingSpecialist` with the explicit goal of migrating its core logic to an external worker process in the future. This ensures our initial implementation is a stepping stone, not a dead end.

## 6.0 Next Steps

1.  Formal approval of this proposal.
2.  Creation of a `TODO_Async_Polling_Model.md` file to guide the implementation of Pattern A.
3.  Begin development of the `PollingSpecialist` and necessary modifications to the `Router` and `GraphState`.
