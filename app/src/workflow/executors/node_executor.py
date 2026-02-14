import logging
import time
import traceback
import hashlib
from typing import Dict, Any, Callable

# AIMessage import removed - create_missing_artifact_response no longer pollutes messages
from langgraph.errors import GraphInterrupt

from ...specialists.base import BaseSpecialist
from ...graph.state import GraphState
from ...utils import state_pruner
from ...utils.errors import SpecialistError, WorkflowError, RateLimitError, CircuitBreakerTriggered
from ...utils.report_schema import ErrorReport
from ...resilience.monitor import InvariantMonitor
from ...llm.tracing import (
    set_current_specialist,
    clear_current_specialist,
    flush_adapter_traces,
    build_specialist_turn_trace,
)

logger = logging.getLogger(__name__)

class NodeExecutor:
    """
    Responsible for creating safe execution wrappers around specialist instances.
    Handles invariant monitoring, error reporting, history tracking, and circuit breaking.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.invariant_monitor = InvariantMonitor(self.config)

    def create_missing_artifact_response(
        self,
        specialist_name: str,
        missing_artifacts: list[str],
        recommended_specialists: list[str]
    ) -> dict:
        """
        Generates a standardized response when required artifacts are missing.

        This returns ONLY scratchpad signals (no messages). The recommendation flows
        through scratchpad.recommended_specialists, which Router reads and injects
        into its prompt context. We intentionally avoid adding to messages because:
        1. This is internal orchestration, not user communication
        2. Adding to messages pollutes the user-visible stream with plumbing details
        3. The dependency context is built by Router from scratchpad, not message content

        CRITICAL: Also adds the blocked specialist to forbidden_specialists so Router
        won't offer it again until the dependency is satisfied. This prevents loops
        where Router keeps routing back to the blocked specialist.
        """
        missing_list = ", ".join(f"'{a}'" for a in missing_artifacts)
        logger.warning(
            f"Specialist '{specialist_name}' blocked: missing artifacts {missing_list}. "
            f"Recommending: {recommended_specialists}. Adding '{specialist_name}' to forbidden_specialists."
        )
        # Only use scratchpad for routing signals - no messages pollution
        # ADR-CORE-016: Add blocked specialist to forbidden_specialists to prevent routing loops
        result = {
            "scratchpad": {
                "recommended_specialists": recommended_specialists,
                "forbidden_specialists": [specialist_name]  # Remove from Router menu
            }
        }
        return result

    def create_safe_executor(self, specialist_instance: BaseSpecialist, streaming_callback: Callable[[str], None] = None) -> Callable[[GraphState], Dict[str, Any]]:
        """
        Creates a wrapper around a specialist's execute method to enforce preconditions
        and provide centralized exception handling.
        """
        specialist_name = specialist_instance.specialist_name
        specialist_config = specialist_instance.specialist_config
        required_artifacts = specialist_config.get("requires_artifacts", [])
        artifact_providers = specialist_config.get("artifact_providers", {})

        def safe_executor(state: GraphState) -> Dict[str, Any]:
            # CENTRALIZED ROUTING HISTORY TRACKING
            # All specialist executions are tracked here for complete observability.
            # This ensures progenitors, subgraph nodes, and all specialists appear in Archive reports.
            routing_entry = specialist_name
            logger.debug(f"safe_executor: Tracking execution of '{specialist_name}'")

            # TASK 1.5: Invariant Monitoring (Pre-Execution)
            # Fail-fast if the system is in an invalid state before executing the specialist.
            # ADR-CORE-016: Menu Filter Pattern - check_invariants may return state updates for loop recovery
            menu_filter_update = None
            try:
                menu_filter_update = self.invariant_monitor.check_invariants(state, stage=f"pre-execution:{specialist_name}")
            except CircuitBreakerTriggered as cbt:
                logger.error(f"Circuit Breaker Triggered in '{specialist_name}': {cbt}")

                if cbt.action == "HALT":
                    raise WorkflowError(f"System Halted by Circuit Breaker: {cbt.reason}") from cbt

                elif cbt.action == "ROUTE_TO_ERROR_HANDLER":
                    # Return a state update that forces routing to the error handler
                    # The decider functions (route_to_next_specialist, etc.) will pick this up.
                    return {
                        "scratchpad": {
                            "stabilization_action": "ROUTE_TO_ERROR_HANDLER",
                            "error_report": f"Circuit Breaker Triggered: {cbt.violation_type}. Reason: {cbt.reason}"
                        },
                        "routing_history": [routing_entry] # Log that we attempted this node
                    }
                else:
                    # Default to HALT for unknown actions
                    raise WorkflowError(f"System Halted by Circuit Breaker (Unknown Action '{cbt.action}'): {cbt.reason}") from cbt

            if required_artifacts:
                is_conditional = isinstance(required_artifacts[0], list)
                if is_conditional:
                    if not any(all(state.get("artifacts", {}).get(a) for a in dep_set) for dep_set in required_artifacts):
                        first_artifact = required_artifacts[0][0]
                        recommended = artifact_providers.get(first_artifact)
                        response = self.create_missing_artifact_response(
                            specialist_name, [f"At least one of {required_artifacts}"], [recommended] if recommended else []
                        )
                        response["routing_history"] = [routing_entry] # Ensure blocked execution is tracked
                        return response
                else:
                    for artifact in required_artifacts:
                        if not state.get("artifacts", {}).get(artifact):
                            recommended = artifact_providers.get(artifact)
                            response = self.create_missing_artifact_response(
                                specialist_name, [artifact], [recommended] if recommended else []
                            )
                            response["routing_history"] = [routing_entry] # Ensure blocked execution is tracked
                            return response

            try:
                # If a streaming callback is provided, use it to signal the start of execution.
                if streaming_callback:
                    streaming_callback(f"Entering node: {specialist_name}\n")

                # --- TRACE CAPTURE: Pre-execution context ---
                start_time = time.perf_counter()
                artifacts_before = list(state.get("artifacts", {}).keys())
                routing_history = state.get("routing_history", [])
                from_source = routing_history[-1] if routing_history else "user"
                step = len(routing_history)

                # Get system prompt for trace
                system_prompt = None
                if hasattr(specialist_instance, 'llm_adapter') and specialist_instance.llm_adapter:
                    if hasattr(specialist_instance.llm_adapter, 'system_prompt'):
                        system_prompt = specialist_instance.llm_adapter.system_prompt
                        logger.debug(f"System prompt for '{specialist_name}':\n---PROMPT---\n{system_prompt}\n---ENDPROMPT---")

                # LLM TRACE CAPTURE: Set current specialist for trace attribution
                set_current_specialist(specialist_name)

                update = specialist_instance.execute(state)

                # --- TRACE CAPTURE: Build complete specialist turn trace ---
                # Issue #35: Emit traces for ALL specialists (LLM and procedural)
                adapter_traces = flush_adapter_traces()
                clear_current_specialist()  # Clean up trace context after flush
                specialist_type = specialist_config.get("type", "llm")
                execution_latency_ms = int((time.perf_counter() - start_time) * 1000)

                # ADR-073 Phase 1: Emit traces for ALL specialists unconditionally.
                # MCP-delegating specialists (PD, TA react mode) have no adapter_traces
                # but still produce artifacts and scratchpad signals worth tracing.
                # Compute artifacts produced (new keys in update)
                artifacts_after = list(update.get("artifacts", {}).keys())
                artifacts_produced = [a for a in artifacts_after if a not in artifacts_before]

                # Extract scratchpad signals written
                scratchpad_signals = update.get("scratchpad", {})

                # Extract routing decision (for router specialist)
                routing_decision = update.get("next_specialist")

                # Build complete trace
                turn_trace = build_specialist_turn_trace(
                    adapter_traces=adapter_traces,
                    step=step,
                    specialist_name=specialist_name,
                    specialist_type=specialist_type,
                    from_source=from_source,
                    system_prompt=system_prompt,
                    context_artifacts_before=artifacts_before,
                    artifacts_produced=artifacts_produced,
                    scratchpad_signals=scratchpad_signals,
                    routing_decision=routing_decision,
                    execution_latency_ms=execution_latency_ms,
                )

                # Add trace to state
                update["llm_traces"] = [turn_trace.model_dump()]
                logger.debug(f"Captured specialist turn trace for '{specialist_name}' (step {step}, type={specialist_type})")

                # CENTRALIZED ROUTING HISTORY TRACKING (post-execution)
                # Remove any routing_history that specialist tried to add (enforces centralization)
                if "routing_history" in update:
                    logger.warning(f"Specialist '{specialist_name}' returned routing_history - ignoring (centralized tracking enforced)")
                    del update["routing_history"]

                # Add centralized routing history entry
                update["routing_history"] = [routing_entry]

                # TASK 3.3: Result Aggregation (Barrier Update)
                # Remove this specialist from the active parallel tasks list.
                # This signals completion to the barrier logic in check_task_completion.
                # Note: The reducer for 'parallel_tasks' handles removal if a string is passed.
                update["parallel_tasks"] = specialist_name

                if "turn_count" in update:
                    logger.warning(f"Specialist '{specialist_name}' returned a 'turn_count'. This is not allowed and will be ignored.")
                    del update["turn_count"]

                # ADR-CORE-016: Menu Filter Lifecycle Management
                # Clear forbidden_specialists after successful execution UNLESS specialist set it itself.
                # Self-exclusion ("not me" pattern) should persist until Router consumes it.
                # Only clear external bans (from InvariantMonitor loop detection).
                if specialist_name != "router_specialist":
                    specialist_set_forbidden = specialist_name in update.get("scratchpad", {}).get("forbidden_specialists", [])
                    if not specialist_set_forbidden:
                        scratchpad_in_update = update.get("scratchpad", {})
                        scratchpad_in_update["forbidden_specialists"] = None
                        update["scratchpad"] = scratchpad_in_update
                        logger.debug(f"Cleared forbidden_specialists after successful execution of '{specialist_name}'")

                # ADR-CORE-016: Merge menu filter updates from InvariantMonitor (if any)
                if menu_filter_update:
                    logger.info(f"Merging menu filter update from InvariantMonitor: {menu_filter_update}")
                    # Merge scratchpad updates
                    if "scratchpad" in menu_filter_update:
                        existing_scratchpad = update.get("scratchpad", {})
                        existing_scratchpad.update(menu_filter_update["scratchpad"])
                        update["scratchpad"] = existing_scratchpad

                # Progressive Loop Detection: Track output hashes for stagnation detection
                # Compute hash of specialist's output to distinguish productive iteration from stuck loops
                update_messages = update.get("messages", [])
                if update_messages:
                    last_message = update_messages[-1]
                    if hasattr(last_message, "content"):
                        # Compute hash of normalized message content
                        content = last_message.content
                        normalized = content.strip()
                        output_hash = hashlib.md5(normalized.encode()).hexdigest()

                        # Update scratchpad with hash history
                        scratchpad_update = update.get("scratchpad", {})
                        output_hashes = scratchpad_update.get("output_hashes") or {}
                        specialist_history = output_hashes.get(specialist_name, [])
                        specialist_history.append(output_hash)
                        specialist_history = specialist_history[-3:]  # Keep only last 3 hashes
                        output_hashes[specialist_name] = specialist_history
                        scratchpad_update["output_hashes"] = output_hashes
                        update["scratchpad"] = scratchpad_update

                        logger.debug(f"Output hash for '{specialist_name}': {output_hash[:8]}... ({len(specialist_history)} in history)")

                return update
            except RateLimitError as e:
                # Rate limit errors are FATAL - halt workflow immediately (fail-fast pattern)
                logger.error(f"Rate limit exceeded in specialist '{specialist_name}': {e}")
                clear_current_specialist()  # Clean up trace context
                flush_adapter_traces()  # Discard any partial traces
                raise WorkflowError(
                    f"Rate limit exceeded for specialist '{specialist_name}'. "
                    f"Please wait before retrying. Error: {e}"
                ) from e
            except GraphInterrupt:
                # ADR-CORE-018: Let interrupt() propagate for HitL workflows
                logger.info(f"Specialist '{specialist_name}' triggered interrupt for user clarification")
                clear_current_specialist()  # Clean up trace context
                # Note: Don't flush traces here - workflow will resume and may want accumulated traces
                raise
            except (SpecialistError, Exception) as e:
                logger.error(f"Caught unhandled exception from specialist '{specialist_name}': {e}", exc_info=True)
                clear_current_specialist()  # Clean up trace context

                # Capture error traces for archive visibility (no more ghost executions)
                error_adapter_traces = flush_adapter_traces()
                execution_latency_ms = int((time.perf_counter() - start_time) * 1000)

                tb_str = traceback.format_exc()
                pruned_state = state_pruner.prune_state(state)
                report_data = ErrorReport(
                    error_message=str(e),
                    traceback=tb_str,
                    routing_history=state.get("routing_history", []),
                    pruned_state=pruned_state
                )
                markdown_report = state_pruner.generate_report(report_data)
                # CENTRALIZED ROUTING HISTORY TRACKING (error case)
                # Ensure failed executions are also tracked for observability
                # NOTE: "error" moved INTO scratchpad because GraphState doesn't define
                # a top-level "error" field - LangGraph would drop it. Issue #70.
                update = {
                    "scratchpad": {
                        "error": f"Specialist '{specialist_name}' failed. See report for details.",
                        "error_report": markdown_report
                    },
                    "routing_history": [routing_entry]
                }

                # Emit error traces so failed specialists appear in llm_traces.jsonl
                if error_adapter_traces:
                    turn_trace = build_specialist_turn_trace(
                        adapter_traces=error_adapter_traces,
                        step=step,
                        specialist_name=specialist_name,
                        specialist_type=specialist_config.get("type", "llm"),
                        from_source=from_source,
                        system_prompt=system_prompt,
                        context_artifacts_before=artifacts_before,
                        artifacts_produced=[],
                        scratchpad_signals={"error": str(e)},
                        routing_decision=None,
                        execution_latency_ms=execution_latency_ms,
                    )
                    update["llm_traces"] = [turn_trace.model_dump()]
                    logger.debug(f"Captured error trace for '{specialist_name}' (step {step})")

                return update

        return safe_executor
