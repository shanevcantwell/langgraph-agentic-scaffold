# ADR PLATFORM 004: Fail-Fast on Unknown Graph Routes

**Date:** 2025-10-06

**Status:** Proposed

## Context

The `langgraph` library's default behavior for conditional edges (`add_conditional_edges`) is to loop back to the source node if the decider function returns a destination key that is not present in the provided destination map.

This was discovered when the `CriticSpecialist` was observed routing back to itself, creating an unproductive loop. The `after_critique_decider` was returning a valid destination, but because the `CriticSpecialist` itself was not in its own destination map, LangGraph defaulted to looping.

This "fail-closed" behavior, while preventing the graph from halting, can hide subtle routing bugs and make debugging difficult. The developer must be meticulously careful to ensure every possible destination is included in every conditional edge map.

## Potential Solution

We will adopt a "fail-fast" policy for all conditional routing within the graph. Instead of relying on LangGraph's default looping behavior, we will enforce that any attempt to route to an unknown destination immediately raises a `WorkflowError`.

This will be implemented by:
1.  Creating a new private helper method, `_add_safe_conditional_edges`, within the `GraphBuilder` class.
2.  This method will wrap the standard `workflow.add_conditional_edges` call.
3.  The `decider` function passed to this wrapper will be augmented to first check if its intended destination exists in the destination map.
4.  If the destination is not found, the augmented decider will raise a `WorkflowError` with a clear message indicating the source node, the invalid destination, and the available destinations.
5.  All calls to `add_conditional_edges` within the `GraphBuilder` will be replaced with calls to our new `_add_safe_conditional_edges` wrapper.

## Code Recommendation for Potential Solution
graph_builder.py
```python
            else:
                workflow.add_node(name, self.orchestrator.create_safe_executor(instance))

    def _add_safe_conditional_edges(self, workflow: StateGraph, source_node: str, decider: Callable, destination_map: Dict[str, str]):
        """
        A wrapper around workflow.add_conditional_edges that enforces a "fail-fast"
        policy. It prevents silent, default looping by raising an error if the
        decider returns a destination not in the explicit map.
        """
        def safe_decider(state: GraphState) -> str:
            destination = decider(state)
            if destination not in destination_map:
                raise WorkflowError(
                    f"Routing error from '{source_node}': Decider returned destination '{destination}', "
                    f"which is not in the configured destination map: {list(destination_map.keys())}."
                )
            return destination

        workflow.add_conditional_edges(source_node, safe_decider, destination_map)

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        router_name = CoreSpecialist.ROUTER.value
        destinations = {name: name for name in self.specialists if name != router_name}
        workflow.add_conditional_edges(router_name, self.orchestrator.route_to_next_specialist, destinations)
        self._add_safe_conditional_edges(workflow, router_name, self.orchestrator.route_to_next_specialist, destinations)

        for name in self.specialists:
            if name in [router_name, CoreSpecialist.RESPONSE_SYNTHESIZER.value, CoreSpecialist.ARCHIVER.value, CoreSpecialist.END.value, CoreSpecialist.CRITIC.value]:
                continue
            workflow.add_conditional_edges(name, self.orchestrator.check_task_completion, {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name})
            self._add_safe_conditional_edges(workflow, name, self.orchestrator.check_task_completion, {CoreSpecialist.END.value: CoreSpecialist.END.value, router_name: router_name})

        if CoreSpecialist.CRITIC.value in self.specialists:
            critic_config = self.config.get("specialists", {}).get(CoreSpecialist.CRITIC.value, {})
            revision_target = critic_config.get("revision_target", router_name)
            workflow.add_conditional_edges(
            self._add_safe_conditional_edges(
                CoreSpecialist.CRITIC.value,
                self.orchestrator.after_critique_decider,
                {
                    revision_target: revision_target,
                    CoreSpecialist.END.value: CoreSpecialist.END.value,
                    router_name: router_name,
                    CoreSpecialist.CRITIC.value: CoreSpecialist.CRITIC.value # Add self to prevent default looping
                    router_name: router_name
                }
            )
```

## Consequences

### Positive
-   **Increased Robustness:** Eliminates a class of silent, hard-to-debug looping errors.
-   **Improved Developer Experience:** Routing errors will be loud, explicit, and immediate, pointing developers directly to the misconfigured edge.
-   **Architectural Clarity:** The system's routing logic becomes more explicit and less reliant on the implicit, potentially surprising, defaults of an underlying library.

### Negative
-   **Minor Abstraction:** Introduces a thin wrapper, slightly increasing the conceptual overhead for developers new to this specific codebase. However, the safety gains are deemed to far outweigh this cost.
-   **Stricter Implementation:** Developers must be more precise when defining conditional edges, but this is considered a positive consequence as it forces more robust design.

This decision makes our graph's behavior more predictable and aligns with a general software engineering principle to fail as early and as loudly as possible when an unexpected state is encountered.