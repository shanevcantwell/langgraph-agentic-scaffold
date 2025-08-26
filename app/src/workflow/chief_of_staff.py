# src/workflow/chief_of_staff.py
import logging
import traceback
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..utils import state_pruner
from ..utils.report_schema import ErrorReport
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..enums import CoreSpecialist
from ..llm.factory import AdapterFactory

logger = logging.getLogger(__name__)

class ChiefOfStaff:
    def __init__(self):
        self.config = ConfigLoader().get_config()

        # Load specialists first, so we know which ones are available.
        self.specialists = self._load_and_configure_specialists()

        # Now, validate the entry point against the list of *loaded* specialists.
        workflow_config = self.config.get("workflow", {})
        raw_entry_point = workflow_config.get("entry_point", CoreSpecialist.ROUTER.value)
        if raw_entry_point not in self.specialists:
            logger.error(
                f"Configured entry point '{raw_entry_point}' is not an available specialist. "
                f"This can happen if it's missing from config.yaml or failed to load. "
                f"Defaulting to '{CoreSpecialist.ROUTER.value}'."
            )
            self.entry_point = CoreSpecialist.ROUTER.value
        else:
            self.entry_point = raw_entry_point

        # Configure loop detection parameters
        self.max_loop_cycles = workflow_config.get("max_loop_cycles", 3)
        # A loop can involve one or more specialists. Start detection at 1.
        self.min_loop_len = 1
        logger.info(f"Loop detection configured with max_loop_cycles={self.max_loop_cycles}")

        self.graph = self._build_graph()
        logger.info(f"---ChiefOfStaff: Graph compiled successfully with entry point '{self.entry_point}'.---")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        """
        Iterates through the validated specialist configurations from ConfigLoader,
        instantiates each specialist class, and logs errors for any that fail,
        allowing the application to start with the successfully loaded specialists.
        """
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                if not issubclass(SpecialistClass, BaseSpecialist):
                    logger.warning(f"Skipping '{name}': Class '{SpecialistClass.__name__}' does not inherit from BaseSpecialist.")
                    continue
                instance = SpecialistClass(name)
                if not instance.is_enabled:
                    logger.warning(f"Specialist '{name}' initialized but is disabled. It will not be added to the graph.")
                    continue

                # The ChiefOfStaff is now responsible for creating and assigning the adapter.
                if config.get("type") == "llm":
                    # Defer adapter creation for special cases to their dedicated methods.
                    if name in [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value]:
                        logger.info(f"Deferring adapter creation for '{name}' to its specialized configuration method.")
                    else:
                        prompt_file = config.get("prompt_file")
                        system_prompt = load_prompt(prompt_file) if prompt_file else ""
                        instance.llm_adapter = AdapterFactory().create_adapter(
                            specialist_name=name,
                            system_prompt=system_prompt
                        )

                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except Exception as e:
                logger.error(f"Failed to load specialist '{name}', it will be disabled. Error: {e}", exc_info=True)
                continue # Allow the app to start with the specialists that did load correctly.

        # This is the key change: only provide the orchestration specialists (Router, Triage)
        # with a list of specialists that were *successfully* loaded. This prevents them
        # from trying to route to a specialist that is configured but failed to start.
        all_configs = self.config.get("specialists", {})
        available_configs = {name: all_configs[name] for name in loaded_specialists.keys() if name in all_configs}

        if CoreSpecialist.ROUTER.value in loaded_specialists:
            self._configure_router(loaded_specialists, available_configs)
        
        # If the Triage specialist exists, configure it with the full map of other specialists.
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, available_configs)

        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        logger.info("Conducting 'morning standup' to configure the router...")
        router_instance = specialists[CoreSpecialist.ROUTER.value]

        # Provide the router with the full map of specialist configurations.
        # It will use this map at runtime to filter specialists based on the routing channel.
        router_instance.set_specialist_map(configs)

        # The static part of the router's prompt, including the full list of specialists.
        # A dynamic, filtered list may be added at runtime by the router itself.
        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        base_prompt_file = router_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""

        # The router needs to know about all other specialists for its prompt.
        available_specialists = {name: conf for name, conf in configs.items() if name != CoreSpecialist.ROUTER.value}
        standup_report = "\n\n--- AVAILABLE SPECIALISTS (Morning Standup) ---\n"
        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]
        standup_report += "\n".join(specialist_descs)

        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Task Completion**: If the last message is a report or summary that appears to fully satisfy the user's request, your job is done. You MUST route to `__end__`.\n"
            "2. **Error Correction**: If the last message is from a specialist reporting an error (e.g., it needs a file to be read first), you MUST use that feedback to select the correct specialist to resolve the issue (e.g., 'file_specialist').\n"
            "3. **Follow the Plan**: If a `system_plan` or other artifact has just been added to the state, you MUST route to the specialist best suited to execute the next step.\n"
            "4. **Use Provided Tools**: You will be provided with a list of specialists to choose from based on the current context. You MUST choose from that list."
        )
        dynamic_system_prompt = f"{base_prompt}{standup_report}\n{feedback_instruction}"        
        
        # Create the adapter from scratch with the final, complete prompt.
        # This ensures the router gets the correct configuration and prompt in one step.
        router_instance.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=CoreSpecialist.ROUTER.value,
            system_prompt=dynamic_system_prompt
        )
        logger.info("RouterSpecialist adapter created with dynamic, context-aware prompt.")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        """Provides the Triage specialist with the map of all other specialists so it can make recommendations."""
        logger.info("Configuring the Triage specialist with a dynamic prompt of system capabilities...")
        triage_instance = specialists[CoreSpecialist.TRIAGE.value]

        # The Triage specialist needs to know about all other functional specialists for its prompt.
        # Exclude orchestration specialists to prevent loops or nonsensical recommendations.
        excluded = [CoreSpecialist.ROUTER.value, CoreSpecialist.TRIAGE.value, CoreSpecialist.ARCHIVER.value]
        available_specialists = {name: conf for name, conf in configs.items() if name not in excluded}
        
        # This call is still useful for the specialist's internal logic.
        triage_instance.set_specialist_map(available_specialists)

        triage_config = configs.get(CoreSpecialist.TRIAGE.value, {})
        base_prompt_file = triage_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""

        specialist_descs = [f"- {name}: {conf.get('description', 'No description available.')}" for name, conf in available_specialists.items()]
        available_specialists_prompt = "\n".join(specialist_descs)
        
        dynamic_system_prompt = f"{base_prompt}\n\n--- AVAILABLE SPECIALISTS ---\nYou MUST choose one or more of the following specialists:\n{available_specialists_prompt}"
        triage_instance.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=CoreSpecialist.TRIAGE.value,
            system_prompt=dynamic_system_prompt
        )
        logger.info("Triage specialist adapter created with dynamic, context-aware prompt.")

    def _create_safe_executor(self, specialist_instance: BaseSpecialist):
        """
        Creates a wrapper around a specialist's execute method to enforce global
        rules like turn count modification and to provide centralized exception
        handling and reporting.
        """
        def safe_executor(state: GraphState) -> Dict[str, Any]:
            try:
                update = specialist_instance.execute(state)
                if "turn_count" in update:
                    logger.warning(
                        f"Specialist '{specialist_instance.specialist_name}' returned a 'turn_count'. "
                        "This is not allowed and will be ignored to preserve the global count."
                    )
                    del update["turn_count"]
                return update
            except Exception as e:
                logger.error(
                    f"Caught unhandled exception from specialist '{specialist_instance.specialist_name}': {e}",
                    exc_info=True
                )
                # Generate a detailed error report for debugging and user feedback.
                tb_str = traceback.format_exc()
                pruned_state = state_pruner.prune_state(state)
                routing_history = state.get("routing_history", [])

                report_data = ErrorReport(
                    error_message=str(e),
                    traceback=tb_str,
                    routing_history=routing_history,
                    pruned_state=pruned_state
                )
                markdown_report = state_pruner.generate_report(report_data)

                # Return an update that halts the graph and provides the report.
                return {
                    "error": f"Specialist '{specialist_instance.specialist_name}' failed. See report for details.",
                    "error_report": markdown_report
                }
        return safe_executor

    def _add_nodes_to_graph(self, workflow: StateGraph):
        """Adds all loaded specialists as nodes to the graph."""
        for name, instance in self.specialists.items():
            if name == CoreSpecialist.ROUTER.value:
                # The router is special; it manages turn count and doesn't need the safe wrapper.
                workflow.add_node(name, instance.execute)
            else:
                # All other specialists are wrapped to prevent them from modifying the turn count.
                workflow.add_node(name, self._create_safe_executor(instance))

    def _wire_hub_and_spoke_edges(self, workflow: StateGraph):
        """Defines the 'hub-and-spoke' architecture for the graph."""
        router_name = CoreSpecialist.ROUTER.value

        # 1. The router is the central hub. All decisions on where to go next flow from it.
        destinations = {name: name for name in self.specialists if name != router_name}
        destinations[END] = END
        workflow.add_conditional_edges(router_name, self.decide_next_specialist, destinations)

        # 2. After any other specialist runs, control must return to the router for the next decision.
        #    This creates the "hub-and-spoke" architecture.
        for name in self.specialists:
            if name == router_name:
                continue  # Don't add an edge from the router to itself.
            if name == CoreSpecialist.ARCHIVER.value:
                workflow.add_edge(name, END)  # The archiver is a terminal node.
            else:
                workflow.add_edge(name, router_name)  # All other specialists loop back to the router.

    def _build_graph(self) -> StateGraph:
        """
        Builds the LangGraph StateGraph by adding nodes and defining the "hub-and-spoke"
        edge architecture.
        """
        workflow = StateGraph(GraphState)
        self._add_nodes_to_graph(workflow)
        self._wire_hub_and_spoke_edges(workflow)

        # Set the validated entry point for the graph.
        workflow.set_entry_point(self.entry_point)
        return workflow.compile()

    def decide_next_specialist(self, state: GraphState) -> str:
        """
        This is now a pure decision function. It reads the state and returns
        the next node's name. It does not and cannot modify the state.
        """
        turn_count = state.get("turn_count", 0)
        # The number of graph steps is roughly 2 * turn_count because of the hub-and-spoke model (Specialist -> Router).
        # This log helps clarify why a recursion limit might be reached.
        approx_steps = (turn_count * 2) + 1
        logger.info(f"--- ChiefOfStaff: Deciding next specialist (Turn: {turn_count}, Approx. Graph Steps: {approx_steps}) ---")
        
        if error := state.get("error"):
            logger.error(f"Error detected in state: '{error}'. Halting workflow.")
            return END

        # --- Intentional Loop Check ---
        # If a specialist is managing its own iterative loop (like WebBuilder),
        # we should bypass the ChiefOfStaff's generic loop detection to avoid
        # prematurely halting a productive, intentional process.
        if (state.get("web_builder_iteration") or 0) > 0:
            logger.info("Intentional refinement loop detected (web_builder_iteration > 0). Bypassing generic loop detection for this turn.")
        else:
            # Check for unproductive loops to prevent the system from getting stuck.
            # This is a more intelligent safeguard than a simple max turn count.
            routing_history = state.get("routing_history", [])
            if len(routing_history) >= self.min_loop_len * self.max_loop_cycles:
                # Iterate through possible loop lengths
                for loop_len in range(self.min_loop_len, (len(routing_history) // self.max_loop_cycles) + 1):
                    # Extract the most recent block, which is our reference pattern
                    last_block = tuple(routing_history[-loop_len:])
                    is_loop = True
                    # Compare it with the preceding blocks
                    for i in range(1, self.max_loop_cycles):
                        start_index = -(i + 1) * loop_len
                        end_index = -i * loop_len
                        preceding_block = tuple(routing_history[start_index:end_index])
                        if last_block != preceding_block:
                            is_loop = False
                            break
                    if is_loop:
                        logger.error(
                            f"Unproductive loop detected. The specialist sequence '{list(last_block)}' "
                            f"has repeated {self.max_loop_cycles} times. Halting workflow."
                        )
                        return END
        
        next_specialist = state.get("next_specialist")
        logger.info(f"Router has selected next specialist: {next_specialist}")

        if next_specialist is None:
            logger.error("Routing Error: The router failed to select a next step. Halting workflow.")
            return END
        
        return next_specialist

    def get_graph(self) -> StateGraph:
        return self.graph
