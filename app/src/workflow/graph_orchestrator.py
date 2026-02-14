# app/src/workflow/graph_orchestrator.py
import logging
import traceback
import hashlib
from typing import Dict, Any, Callable

from langchain_core.messages import AIMessage
from langgraph.errors import GraphInterrupt

from ..specialists.base import BaseSpecialist
from ..graph.state import GraphState, Scratchpad
from ..enums import CoreSpecialist
from ..utils.errors import WorkflowError

from ..interface.context_schema import ContextPlan
from .specialist_categories import SpecialistCategories

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

                # ADR-CORE-018: Route ALL plans with actions through Facilitator chain
                # Flow: Facilitator (autonomous) → Dialogue (interactive) → Router
                # - Facilitator executes automated actions (READ_FILE, RESEARCH, etc.)
                # - Facilitator ignores ASK_USER actions (passes context_plan through)
                # - Dialogue checks for remaining ASK_USER actions and triggers interrupt()

                if plan.actions:
                    ask_user_count = sum(1 for a in plan.actions if a.type == "ask_user")
                    other_count = len(plan.actions) - ask_user_count
                    logger.info(
                        f"Triage produced plan with {other_count} context-gathering and "
                        f"{ask_user_count} ask_user actions. Routing to Facilitator chain."
                    )
                    return "facilitator_specialist"

                # Empty plan (no actions at all) - route to Router
                logger.info("Triage produced empty plan. Routing to Router.")
            except Exception as e:
                logger.error(f"Failed to parse ContextPlan in check_triage_outcome: {e}")
        
        logger.info("Triage produced no actions. Routing to Router.")
        return CoreSpecialist.ROUTER.value

    def _check_stabilization_action(self, state: GraphState) -> str | None:
        """
        Checks if a stabilization action (Circuit Breaker) has been triggered.
        Returns the target specialist name if an action is present, else None.

        Issue #161: Routes to Exit Interview (can evaluate recoverability)
        instead of the non-existent 'error_handling_specialist'.
        Falls back to END if Exit Interview is not loaded.
        """
        action = state.get("scratchpad", {}).get("stabilization_action")
        if action == "ROUTE_TO_ERROR_HANDLER":
            if CoreSpecialist.EXIT_INTERVIEW.value in self.specialists:
                logger.warning("Stabilization action detected. Routing to Exit Interview for evaluation.")
                return CoreSpecialist.EXIT_INTERVIEW.value
            logger.warning("Stabilization action detected. No Exit Interview available. Routing to END.")
            return CoreSpecialist.END.value
        return None

    def _route_pathological(self, reason: str) -> str:
        """
        Issue #161: Guarded routing for pathological interrupts with fallback chain.

        Tries: interrupt_evaluator → exit_interview → router
        """
        if "interrupt_evaluator_specialist" in self.specialists:
            logger.info(f"classify_interrupt: PATHOLOGICAL ({reason}) → Interrupt Evaluator")
            return "interrupt_evaluator_specialist"
        if CoreSpecialist.EXIT_INTERVIEW.value in self.specialists:
            logger.info(f"classify_interrupt: PATHOLOGICAL ({reason}) → Exit Interview (no Interrupt Evaluator)")
            return CoreSpecialist.EXIT_INTERVIEW.value
        logger.warning(f"classify_interrupt: PATHOLOGICAL ({reason}) → Router (no IE, no EI)")
        return CoreSpecialist.ROUTER.value

    def check_task_completion(self, state: GraphState) -> str:
        if state.get("task_is_complete"):
            # ADR-ROADMAP-001: Gate task_is_complete through exit_interview
            # Only allow direct END if exit_interview just validated it
            routing_history = state.get("routing_history", [])
            if routing_history and routing_history[-1] == CoreSpecialist.EXIT_INTERVIEW.value:
                # Exit interview validated - proceed to END
                logger.info(f"--- GraphOrchestrator: Task validated by exit_interview. Routing to {CoreSpecialist.END.value}. ---")
                return CoreSpecialist.END.value

            # Skip EI for conversational specialists with no success criteria
            last_specialist = routing_history[-1] if routing_history else None
            if last_specialist in SpecialistCategories.SKIP_EXIT_INTERVIEW:
                logger.info(f"--- GraphOrchestrator: {last_specialist} complete, skipping exit_interview (no criteria). ---")
                return CoreSpecialist.END.value

            # Specialist claimed complete - validate via exit_interview first
            logger.info(f"--- GraphOrchestrator: task_is_complete set by specialist. Routing to exit_interview for validation. ---")
            return CoreSpecialist.EXIT_INTERVIEW.value

        if self._is_unproductive_loop(state):
            # ADR-ROADMAP-001: Route loops through exit_interview for validation
            logger.info("Unproductive loop in check_task_completion - routing to exit_interview")
            return CoreSpecialist.EXIT_INTERVIEW.value

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
                    # Issue #111: Set loop_detected (informational) instead of termination_reason (abort)
                    # Exit Interview will validate whether the task is truly stuck before we abort.
                    # This prevents stale termination_reason when Exit Interview says COMPLETE.
                    loop_info = {
                        "detected": True,
                        "sequence": list(last_block),
                        "cycles": self.max_loop_cycles
                    }
                    state.setdefault("scratchpad", {})["loop_detected"] = loop_info
                    logger.warning(
                        f"Loop pattern detected: sequence '{list(last_block)}' repeated {self.max_loop_cycles} times. "
                        "Routing to Exit Interview for validation."
                    )
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

        # ADR-ROADMAP-001 Phase 1: Route through exit_interview for completion validation
        # instead of going directly to END on safety triggers
        if self._is_unproductive_loop(state):
            logger.info("Unproductive loop detected - routing to exit_interview for validation")
            return CoreSpecialist.EXIT_INTERVIEW.value

        next_specialist = state.get("next_specialist")
        if not next_specialist:
            logger.error("Routing Error: Router failed to select a next step.")
            logger.info("Routing to exit_interview for completion check before END")
            return CoreSpecialist.EXIT_INTERVIEW.value

        # ADR-CORE-061: Kludge REMOVED
        # The old intercept (lines 214-219) that redirected END → Exit Interview
        # has been replaced by classify_interrupt() wired into the graph.
        # Non-terminal specialists now route through classify_interrupt which
        # handles completion checking properly.

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

    def after_project_director(self, state: GraphState) -> str:
        """
        Decides next step after ProjectDirector.
        """
        scratchpad = state.get("scratchpad", {})
        next_worker = scratchpad.get("next_worker")
        
        if next_worker == "web_specialist":
            return "web_specialist"
        elif next_worker == "router":
            return CoreSpecialist.ROUTER.value
        else:
            logger.warning(f"ProjectDirector returned unknown next_worker: {next_worker}. Defaulting to Router.")
            return CoreSpecialist.ROUTER.value

    def after_web_specialist(self, state: GraphState) -> str:
        """
        Decides next step after WebSpecialist.
        #170: Emergent Project Subgraph removed — always return to Router.
        """
        return CoreSpecialist.ROUTER.value

    def after_exit_interview(self, state: GraphState) -> str:
        """
        ADR-ROADMAP-001 Phase 1: Decides next step after ExitInterviewSpecialist.

        ExitInterviewSpecialist validates if the task is truly complete:
        - If complete: Sets task_is_complete=True → route to END
        - If incomplete: Route through Facilitator to refresh gathered_context

        This gates premature termination by validating accumulated state
        satisfies the original user request.

        Issue #111: Deferred termination_reason
        - If loop_detected was set, we only set termination_reason AFTER Exit Interview
          confirms the task is truly stuck (INCOMPLETE after loop detection)
        - If Exit Interview says COMPLETE despite loop pattern, we don't abort

        When incomplete, we route through Facilitator (not directly to Router) so that
        gathered_context is refreshed with current filesystem state. This prevents
        thrashing where specialists see stale context and repeat their work.
        """
        scratchpad = state.get("scratchpad", {})
        loop_detected = scratchpad.get("loop_detected")

        if state.get("task_is_complete"):
            # Issue #111: Task is done - clear loop_detected if present (consumed, not acted on)
            if loop_detected:
                logger.info("Exit Interview: COMPLETE despite loop pattern - clearing loop_detected")
                scratchpad.pop("loop_detected", None)
            logger.info("--- Exit Interview: Task validated as COMPLETE. Routing to END. ---")
            return CoreSpecialist.END.value

        # Task incomplete
        # Issue #111: If loop was detected AND Exit Interview confirms stuck, NOW abort
        if loop_detected:
            sequence = loop_detected.get("sequence", [])
            cycles = loop_detected.get("cycles", 3)
            termination_reason = (
                f"The workflow is stuck in an unproductive loop and has been halted. "
                f"The sequence '{sequence}' was repeated {cycles} times, and Exit Interview "
                f"confirmed the task is incomplete."
            )
            logger.error(termination_reason)
            scratchpad["termination_reason"] = termination_reason
            scratchpad.pop("loop_detected", None)  # Consumed
            logger.info("--- Exit Interview: INCOMPLETE + loop confirmed. Aborting. ---")
            return CoreSpecialist.END.value

        # Normal incomplete - route through Facilitator to refresh context before retry
        # Facilitator re-executes context_plan, updating gathered_context with current state
        if "facilitator_specialist" in self.specialists:
            logger.info("--- Exit Interview: Task INCOMPLETE. Routing to Facilitator to refresh context. ---")
            return "facilitator_specialist"

        # Fallback if no facilitator (shouldn't happen in normal config)
        logger.info("--- Exit Interview: Task INCOMPLETE. Routing back to Router. ---")
        return CoreSpecialist.ROUTER.value

    # =========================================================================
    # ADR-CORE-061: Tiered Interrupt Architecture
    # =========================================================================

    def classify_interrupt(self, state: GraphState) -> str:
        """
        ADR-CORE-061: Tier 1 - Procedural interrupt classification. No LLM needed.

        This is the first line of defense for interrupt handling. It classifies
        interrupts by type and routes appropriately:

        - TERMINAL: user_abort → End (immediate termination)
        - BENIGN: max_iterations_exceeded, context_overflow → Facilitator (seamless continue)
        - PATHOLOGICAL: stagnation, tool_error, stutter → Interrupt Evaluator (needs LLM)
        - NORMAL + artifacts → Exit Interview (semantic completion check)
        - NORMAL + no artifacts → Router (continue workflow)

        Key principle: The model never stopped. BENIGN interrupts are infrastructure
        pauses that the model should be unaware of. Only PATHOLOGICAL interrupts need
        semantic judgment about recoverability.
        """
        # Issue #161: Check for circuit breaker stabilization action first
        stabilization_target = self._check_stabilization_action(state)
        if stabilization_target:
            return stabilization_target

        scratchpad = state.get("scratchpad", {})
        artifacts = state.get("artifacts", {})

        # === TERMINAL: Immediate end, no evaluation ===
        if scratchpad.get("user_abort"):
            logger.info("classify_interrupt: TERMINAL (user_abort) → End")
            return CoreSpecialist.END.value

        # === BENIGN: Route through Exit Interview for feedback ===
        # max_iterations_exceeded: Arbitrary limit hit, trace is healthy
        # EI provides "INCOMPLETE" feedback that router needs to continue the loop
        # Flow: EI → after_exit_interview → facilitator → router → back to specialist
        if artifacts.get("max_iterations_exceeded") or scratchpad.get("max_iterations_exceeded"):
            logger.info("classify_interrupt: BENIGN (max_iterations) → Exit Interview for feedback")
            return CoreSpecialist.EXIT_INTERVIEW.value

        # context_overflow: Context bloat - compress and continue
        if scratchpad.get("context_overflow"):
            if "facilitator_specialist" in self.specialists:
                logger.info("classify_interrupt: BENIGN (context_overflow) → Facilitator (compress and continue)")
                return "facilitator_specialist"
            logger.info("classify_interrupt: BENIGN (context_overflow) → Router (no facilitator)")
            return CoreSpecialist.ROUTER.value

        # === PATHOLOGICAL: Needs LLM judgment on recoverability ===
        # Issue #161: All pathological paths use guarded routing with fallback chain
        if scratchpad.get("stagnation_detected"):
            return self._route_pathological("stagnation_detected")

        if scratchpad.get("tool_error"):
            return self._route_pathological("tool_error")

        # === NORMAL FLOW: No interrupt ===
        # Produced artifacts? Exit Interview evaluates semantic completion
        if artifacts:
            logger.info("classify_interrupt: Normal flow, artifacts present → Exit Interview")
            return CoreSpecialist.EXIT_INTERVIEW.value

        # No artifacts, no interrupt → Router picks next specialist
        logger.info("classify_interrupt: Normal flow, no artifacts → Router")
        return CoreSpecialist.ROUTER.value

