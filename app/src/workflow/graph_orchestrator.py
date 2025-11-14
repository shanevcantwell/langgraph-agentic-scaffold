# app/src/workflow/graph_orchestrator.py
import logging
import traceback
from typing import Dict, Any, Callable

from langchain_core.messages import AIMessage

from ..specialists.base import BaseSpecialist
from ..graph.state import GraphState, Scratchpad
from ..enums import CoreSpecialist
from ..utils import state_pruner
from ..utils.errors import SpecialistError, WorkflowError, RateLimitError
from ..utils.report_schema import ErrorReport

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

    def after_critique_decider(self, state: GraphState) -> str:
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
        # Check if web_builder was blocked (safe_executor set recommended_specialists)
        if state.get("recommended_specialists"):
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
        turn_count = state.get("turn_count", 0)
        logger.info(f"--- GraphOrchestrator: Routing from Router (Turn: {turn_count}) ---")

        if self._is_unproductive_loop(state):
            return CoreSpecialist.END.value

        next_specialist = state.get("next_specialist")
        if not next_specialist:
            logger.error("Routing Error: Router failed to select a next step. Halting.")
            return CoreSpecialist.END.value

        # TASK 1.2: Validate route before execution (fail-fast on invalid routes)
        if self.allowed_destinations and next_specialist not in self.allowed_destinations:
            error_msg = (
                f"Invalid routing destination '{next_specialist}' selected by router. "
                f"This destination is not a valid node in the graph. "
                f"Allowed destinations: {sorted(self.allowed_destinations)}"
            )
            logger.error(error_msg)
            raise WorkflowError(error_msg)

        # CORE-CHAT-002: Intercept chat_specialist routing and decide between simple/tiered modes
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
        result = {"messages": [ai_message], "recommended_specialists": recommended_specialists}
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