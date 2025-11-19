# app/src/workflow/graph_orchestrator.py
import logging
import traceback
from typing import Dict, Any, Callable

from langchain_core.messages import AIMessage

from ..specialists.base import BaseSpecialist
from ..graph.state import GraphState, Scratchpad
from ..enums import CoreSpecialist
from ..utils import state_pruner
from ..utils.errors import SpecialistError, WorkflowError, RateLimitError, CircuitBreakerTriggered
from ..utils.report_schema import ErrorReport
from ..resilience.monitor import InvariantMonitor

from ..interface.context_schema import ContextPlan

logger = logging.getLogger(__name__)

class GraphOrchestrator:
    """
    Handles the run-time execution logic of the agentic workflow.
    This class contains all the decider functions that the compiled graph
    calls to determine the next step in the workflow.
    """
    def __init__(self, config: Dict[str, Any], specialists: Dict[str, Any], allowed_destinations: set[str] = None):
        self.config = config
        self.specialists = specialists
        self.allowed_destinations = allowed_destinations or set()
        workflow_config = self.config.get("workflow", {})
        self.max_loop_cycles = workflow_config.get("max_loop_cycles", 3)
        self.min_loop_len = 1
        self.invariant_monitor = InvariantMonitor(self.config)

    def check_triage_outcome(self, state: GraphState) -> str:
        """
        Decides next step after TriageArchitect.
        If ContextPlan has actions -> Facilitator.
        Else -> Router.
        """
        artifacts = state.get("artifacts", {})
        context_plan_data = artifacts.get("context_plan")
        
        if context_plan_data:
            try:
                plan = ContextPlan(**context_plan_data)
                if plan.actions:
                    logger.info(f"Triage produced plan with {len(plan.actions)} actions. Routing to Facilitator.")
                    return "facilitator_specialist"
            except Exception as e:
                logger.error(f"Failed to parse ContextPlan in check_triage_outcome: {e}")
        
        logger.info("Triage produced no actions. Routing to Router.")
        return CoreSpecialist.ROUTER.value

    def _check_stabilization_action(self, state: GraphState) -> str | None:
        """
        Checks if a stabilization action (Circuit Breaker) has been triggered.
        Returns the target specialist name if an action is present, else None.
        """
        action = state.get("scratchpad", {}).get("stabilization_action")
        if action == "ROUTE_TO_ERROR_HANDLER":
            logger.warning("Stabilization action 'ROUTE_TO_ERROR_HANDLER' detected. Forcing route to 'error_handling_specialist'.")
            return "error_handling_specialist"
        return None

    def after_critique_decider(self, state: GraphState) -> str:
        # Check for stabilization action first
        stabilization_target = self._check_stabilization_action(state)
        if stabilization_target:
            return stabilization_target

        decision = state.get("scratchpad", {}).get("critique_decision")
        logger.info(f"--- GraphOrchestrator: After Critique. Decision: {decision} ---")
        critic_config = self.config.get("specialists", {}).get(CoreSpecialist.CRITIC.value, {})
        revision_target = critic_config.get("revision_target", CoreSpecialist.ROUTER.value)

        if decision == "REVISE":
            logger.info(f"Routing to configured revision target: {revision_target}")
            return revision_target
        elif decision == "ACCEPT":
            return self.check_task_completion(state)
        else:
            return CoreSpecialist.ROUTER.value

    def after_web_builder(self, state: GraphState) -> str:
        """
        Conditional edge after web_builder (ADR-CORE-012 subgraph).
        Only route to critic if web_builder succeeded.
        If blocked by safe_executor, return to router for dependency resolution.
        """
        # Check for stabilization action first
        stabilization_target = self._check_stabilization_action(state)
        if stabilization_target:
            return stabilization_target

        # Check if web_builder was blocked (safe_executor set recommended_specialists)
        if state.get("scratchpad", {}).get("recommended_specialists"):
            logger.info("after_web_builder: web_builder blocked - returning to router for dependency resolution")
            return CoreSpecialist.ROUTER.value

        # Check if web_builder produced its artifact
        if state.get("artifacts", {}).get("html_document.html"):
            logger.info("after_web_builder: web_builder succeeded - routing to critic for review")
            return CoreSpecialist.CRITIC.value

        # Fallback to router if no artifact produced
        logger.warning("after_web_builder: web_builder did not produce artifact - returning to router")
        return CoreSpecialist.ROUTER.value

    def check_task_completion(self, state: GraphState) -> str:
        if state.get("task_is_complete"):
            logger.info(f"--- GraphOrchestrator: Task completion signal received. Routing to {CoreSpecialist.END.value}. ---")
            return CoreSpecialist.END.value

        if self._is_unproductive_loop(state):
            return CoreSpecialist.END.value

        # TASK 3.3: Result Aggregation (Barrier Logic)
        # Check if there are still active parallel tasks.
        # If so, terminate this branch (return END) to wait for others.
        # If not, proceed to Router (aggregation complete).
        parallel_tasks = state.get("parallel_tasks", [])
        if parallel_tasks:
            logger.info(f"--- GraphOrchestrator: Parallel tasks pending {parallel_tasks}. Terminating branch to wait for completion. ---")
            # We return END to terminate this specific branch of execution.
            # LangGraph will keep the workflow alive as long as other branches are running.
            # When the LAST branch finishes, parallel_tasks will be empty, and it will route to ROUTER.
            return CoreSpecialist.END.value

        logger.info("--- GraphOrchestrator: Task not complete. Returning to Router. ---")
        return CoreSpecialist.ROUTER.value

    def _is_unproductive_loop(self, state: GraphState) -> bool:
        routing_history = state.get("routing_history", [])
        if len(routing_history) >= self.min_loop_len * self.max_loop_cycles:
            for loop_len in range(self.min_loop_len, (len(routing_history) // self.max_loop_cycles) + 1):
                last_block = tuple(routing_history[-loop_len:])
                is_loop = True
                for i in range(1, self.max_loop_cycles):
                    start_index = -(i + 1) * loop_len
                    end_index = -i * loop_len
                    if len(routing_history) < abs(start_index): continue
                    preceding_block = tuple(routing_history[start_index:end_index])
                    if last_block != preceding_block:
                        is_loop = False
                        break
                if is_loop:
                    termination_reason = (f"The workflow is stuck in an unproductive loop and has been halted. "
                                          f"The sequence '{list(last_block)}' was repeated {self.max_loop_cycles} times.")
                    logger.error(termination_reason)
                    # Add the reason to the scratchpad so the EndSpecialist can report it.
                    state.setdefault("scratchpad", {})["termination_reason"] = termination_reason
                    return True
        return False

    def route_to_next_specialist(self, state: GraphState) -> str | list[str]:
        """
        Routes from RouterSpecialist to the next specialist(s).

        Can return either:
        - A single specialist name (str) for normal routing
        - A list of specialist names (list[str]) for parallel fan-out execution

        Special case: When routing to 'chat_specialist', triggers the tiered chat
        subgraph (CORE-CHAT-002) by fanning out to both progenitor specialists in parallel.
        """
        # Check for stabilization action first
        stabilization_target = self._check_stabilization_action(state)
        if stabilization_target:
            return stabilization_target

        turn_count = state.get("turn_count", 0)
        logger.info(f"--- GraphOrchestrator: Routing from Router (Turn: {turn_count}) ---")

        if self._is_unproductive_loop(state):
            return CoreSpecialist.END.value

        next_specialist = state.get("next_specialist")
        if not next_specialist:
            logger.error("Routing Error: Router failed to select a next step. Halting.")
            return CoreSpecialist.END.value

        # TASK 1.2: Validate route before execution (fail-fast on invalid routes)
        # TASK 3.1: Support parallel routing (list of specialists)
        destinations_to_validate = next_specialist if isinstance(next_specialist, list) else [next_specialist]
        
        if self.allowed_destinations:
            invalid_destinations = [dest for dest in destinations_to_validate if dest not in self.allowed_destinations]
            if invalid_destinations:
                error_msg = (
                    f"Invalid routing destination(s) '{invalid_destinations}' selected by router. "
                    f"These destinations are not valid nodes in the graph. "
                    f"Allowed destinations: {sorted(self.allowed_destinations)}"
                )
                logger.error(error_msg)
                raise WorkflowError(error_msg)

        # TASK 3.3: Result Aggregation (Scatter-Gather Synchronization)
        # If routing to multiple specialists, initialize the parallel_tasks list in state.
        # This allows check_task_completion to act as a barrier/join node.
        if isinstance(next_specialist, list) and len(next_specialist) > 1:
            logger.info(f"Initializing parallel execution barrier for: {next_specialist}")
            # We can't update state directly here (this is an edge function).
            # However, the RouterSpecialist (which just ran) could have set this if it knew.
            # Since it didn't, we rely on the fact that check_task_completion will see the
            # parallel_tasks state if we can somehow inject it.
            #
            # CRITICAL LIMITATION: Edge functions cannot update state.
            #
            # Workaround: We assume the RouterSpecialist (or the node that called this)
            # has ALREADY set 'parallel_tasks' in the state if it intended parallel execution.
            # But RouterSpecialist is generic.
            #
            # Alternative: We accept that we cannot set state here.
            # The 'parallel_tasks' field in GraphState must be set by the Router node itself.
            # We need to update RouterSpecialist._execute_logic to set this field.
            pass

        # CORE-CHAT-002: Intercept chat_specialist routing and decide between simple/tiered modes
        # Note: This logic currently only applies if chat_specialist is the ONLY destination.
        # If chat_specialist is part of a parallel group, we assume simple mode or need to refactor.
        if next_specialist == "chat_specialist":
            # Check user preference for simple vs tiered chat mode
            use_simple_chat = state.get("scratchpad", {}).get("use_simple_chat", False)

            if use_simple_chat:
                logger.info("Simple chat mode requested - routing to single chat_specialist")
                return "chat_specialist"

            # Default: Use tiered chat if components are available
            if ("progenitor_alpha_specialist" in self.specialists and
                "progenitor_bravo_specialist" in self.specialists and
                "tiered_synthesizer_specialist" in self.specialists):
                logger.info("Tiered chat mode (default) - fanning out to parallel progenitors (CORE-CHAT-002)")
                fanout_destinations = ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]

                # TASK 1.2: Validate fanout destinations
                if self.allowed_destinations:
                    invalid_fanout = [dest for dest in fanout_destinations if dest not in self.allowed_destinations]
                    if invalid_fanout:
                        error_msg = (
                            f"Invalid fanout routing: destinations {invalid_fanout} are not valid nodes in the graph. "
                            f"Allowed destinations: {sorted(self.allowed_destinations)}"
                        )
                        logger.error(error_msg)
                        raise WorkflowError(error_msg)

                return fanout_destinations
            else:
                logger.warning("Tiered chat subgraph incomplete - falling back to single chat_specialist")
                return "chat_specialist"

        # DISTILLATION SUBGRAPH: Virtual coordinator pattern
        # Router selects "distillation_specialist" (virtual) → map to actual coordinator
        if next_specialist == "distillation_specialist":
            if "distillation_coordinator_specialist" in self.specialists:
                logger.info("Virtual coordinator: routing 'distillation_specialist' → 'distillation_coordinator_specialist'")
                return "distillation_coordinator_specialist"
            else:
                logger.error("Distillation subgraph incomplete - coordinator not found")
                return CoreSpecialist.END.value

        return next_specialist

    def should_continue_expanding(self, state: GraphState) -> str:
        """
        Edge function for distillation expansion loop.
        Checks if more seeds need to be expanded.

        Returns:
            "distillation_prompt_expander_specialist" if more seeds to expand
            "distillation_coordinator_specialist" if expansion complete
        """
        dist_state = state.get("distillation_state", {})
        seed_prompts = dist_state.get("seed_prompts", [])
        expansion_index = dist_state.get("expansion_index", 0)

        if expansion_index < len(seed_prompts):
            logger.info(f"Distillation: More seeds to expand ({expansion_index}/{len(seed_prompts)}) - continuing expansion")
            return "distillation_prompt_expander_specialist"
        else:
            logger.info(f"Distillation: All seeds expanded ({expansion_index}/{len(seed_prompts)}) - returning to coordinator")
            return "distillation_coordinator_specialist"

    def should_continue_collecting(self, state: GraphState) -> str:
        """
        Edge function for distillation collection loop.
        Checks if more prompts need teacher responses.

        Returns:
            "distillation_response_collector_specialist" if more prompts to collect
            "distillation_coordinator_specialist" if collection complete
        """
        dist_state = state.get("distillation_state", {})
        expanded_prompts = dist_state.get("expanded_prompts", [])
        collection_index = dist_state.get("collection_index", 0)

        if collection_index < len(expanded_prompts):
            logger.info(f"Distillation: More prompts to collect ({collection_index}/{len(expanded_prompts)}) - continuing collection")
            return "distillation_response_collector_specialist"
        else:
            logger.info(f"Distillation: All prompts collected ({collection_index}/{len(expanded_prompts)}) - returning to coordinator")
            return "distillation_coordinator_specialist"

    def create_missing_artifact_response(
        self,
        specialist_name: str,
        missing_artifacts: list[str],
        recommended_specialists: list[str]
    ) -> dict:
        """
        Generates a standardized response when required artifacts are missing.
        """
        missing_list = ", ".join(f"'{a}'" for a in missing_artifacts)
        content = (
            f"I, {specialist_name}, cannot execute because the following required artifacts "
            f"are missing from the current state: {missing_list}. "
            f"I recommend running the following specialist(s) first: {', '.join(recommended_specialists)}."
        )
        ai_message = AIMessage(content=content, name=specialist_name)
        result = {
            "messages": [ai_message],
            "scratchpad": {"recommended_specialists": recommended_specialists}
        }
        logger.warning(f"create_missing_artifact_response returning: recommended_specialists={recommended_specialists}")
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
            try:
                self.invariant_monitor.check_invariants(state, stage=f"pre-execution:{specialist_name}")
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
                        return self.create_missing_artifact_response(
                            specialist_name, [f"At least one of {required_artifacts}"], [recommended] if recommended else []
                        )
                else:
                    for artifact in required_artifacts:
                        if not state.get("artifacts", {}).get(artifact):
                            recommended = artifact_providers.get(artifact)
                            return self.create_missing_artifact_response(
                                specialist_name, [artifact], [recommended] if recommended else []
                            )

            try:
                # If a streaming callback is provided, use it to signal the start of execution.
                if streaming_callback:
                    streaming_callback(f"Entering node: {specialist_name}\n")

                # Log the system prompt for LLM-based specialists for better observability.
                if hasattr(specialist_instance, 'llm_adapter') and specialist_instance.llm_adapter:
                    if hasattr(specialist_instance.llm_adapter, 'system_prompt'):
                        logger.debug(f"System prompt for '{specialist_name}':\n---PROMPT---\n{specialist_instance.llm_adapter.system_prompt}\n---ENDPROMPT---")

                update = specialist_instance.execute(state)

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
                return update
            except RateLimitError as e:
                # Rate limit errors are FATAL - halt workflow immediately (fail-fast pattern)
                logger.error(f"Rate limit exceeded in specialist '{specialist_name}': {e}")
                raise WorkflowError(
                    f"Rate limit exceeded for specialist '{specialist_name}'. "
                    f"Please wait before retrying. Error: {e}"
                ) from e
            except (SpecialistError, Exception) as e:
                logger.error(f"Caught unhandled exception from specialist '{specialist_name}': {e}", exc_info=True)
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
                return {
                    "error": f"Specialist '{specialist_name}' failed. See report for details.",
                    "scratchpad": {"error_report": markdown_report},  # Task 2.7: moved to scratchpad
                    "routing_history": [routing_entry]
                }

        return safe_executor