# src/workflow/chief_of_staff.py
import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
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
        self.min_loop_len = 2 # A loop must involve at least 2 specialists
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
                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except Exception as e:
                logger.error(f"Failed to load specialist '{name}', it will be disabled. Error: {e}", exc_info=True)
                continue # Allow the app to start with the specialists that did load correctly.

        # The router configuration needs the full list of potential specialists from the config,
        # not just the ones that loaded, so it can report on them.
        if CoreSpecialist.ROUTER.value in loaded_specialists:
            self._configure_router(loaded_specialists, self.config.get("specialists", {}))
        
        # If the Triage specialist exists, configure it with the full map of other specialists.
        if CoreSpecialist.TRIAGE.value in loaded_specialists:
            self._configure_triage(loaded_specialists, self.config.get("specialists", {}))

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
        router_instance.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=CoreSpecialist.ROUTER.value,
            system_prompt=dynamic_system_prompt
        )
        logger.info("RouterSpecialist adapter re-initialized with dynamic, context-aware prompt.")
        logger.debug(f"RouterSpecialist dynamic system prompt: {dynamic_system_prompt}")

    def _configure_triage(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        """Provides the Triage specialist with the map of all other specialists so it can make recommendations."""
        logger.info("Configuring the Triage specialist with the system's capabilities...")
        triage_instance = specialists[CoreSpecialist.TRIAGE.value]
        triage_instance.set_specialist_map(configs)

    def _create_safe_executor(self, specialist_instance: BaseSpecialist):
        """
        Creates a wrapper around a specialist's execute method to enforce
        the rule that only the router can modify the 'turn_count'.
        This prevents other specialists from accidentally resetting the counter.
        """
        def safe_executor(state: GraphState) -> Dict[str, Any]:
            update = specialist_instance.execute(state)
            if "turn_count" in update:
                logger.warning(
                    f"Specialist '{specialist_instance.specialist_name}' returned a 'turn_count'. "
                    "This is not allowed and will be ignored to preserve the global count."
                )
                del update["turn_count"]
            return update
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
        logger.info("--- ChiefOfStaff: Deciding next specialist ---")
        
        if error := state.get("error"):
            logger.error(f"Error detected in state: '{error}'. Halting workflow.")
            return END

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
