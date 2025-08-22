# src/workflow/chief_of_staff.py
import logging
from typing import Dict
from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..enums import CoreSpecialist
from ..llm.factory import AdapterFactory

logger = logging.getLogger(__name__)
MAX_TURNS = 10

class ChiefOfStaff:
    def __init__(self):
        self.config = ConfigLoader().get_config()
        self.specialists = self._load_and_configure_specialists()
        self.graph = self._build_graph()
        logger.info("---ChiefOfStaff: Graph compiled successfully.---")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        # This method is correct and remains unchanged.
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                if not issubclass(SpecialistClass, BaseSpecialist):
                    logger.warning(f"Skipping '{name}': Class '{SpecialistClass.__name__}' does not inherit from BaseSpecialist.")
                    continue
                instance = SpecialistClass(name)
                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except Exception as e:
                logger.error(f"Failed to instantiate specialist '{name}': {e}", exc_info=True)
                raise
        if CoreSpecialist.ROUTER.value in loaded_specialists:
            self._configure_router(loaded_specialists, specialists_config)
        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        # This method is correct and remains unchanged.
        logger.info("Conducting 'morning standup' to configure the router...")
        router_instance = specialists[CoreSpecialist.ROUTER.value]

        # Provide the router with a list of valid destinations for self-correction.
        available_specialist_names = [name for name in configs if name != CoreSpecialist.ROUTER.value]
        router_instance.set_available_specialists(available_specialist_names)

        router_config = configs.get(CoreSpecialist.ROUTER.value, {})
        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in configs.items() if name != CoreSpecialist.ROUTER.value]
        tools_list_str = "\n".join(available_tools_desc)
        base_prompt_file = router_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""
        # Add a specific instruction to prioritize feedback from other specialists.
        # This helps break reasoning loops where the LLM gets stuck on the initial prompt.
        feedback_instruction = (
            "\nIMPORTANT ROUTING INSTRUCTIONS:\n"
            "1. **Task Completion**: If the last message is a report or summary that appears to fully satisfy the user's request, your job is done. You MUST route to `__end__`.\n"
            "2. **Error Correction**: If the last message is from a specialist reporting an error (e.g., it needs a file to be read first), you MUST use that feedback to select the correct specialist to resolve the issue (e.g., 'file_specialist').\n"
            "3. **Data Processing**: If the last message is an `AIMessage` from the `file_specialist` indicating a file's content has been successfully read and is now in context, and the user's request requires understanding or summarizing that content, your next step MUST be to route to an analysis specialist like 'text_analysis_specialist'.\n"
            "4. **Plan Execution**: If a `system_plan` artifact has just been added to the state, you MUST route to the specialist best suited to execute that plan (e.g., `web_builder` for web content, or another coding specialist for other tasks)."
        )
        dynamic_system_prompt = (
            f"{base_prompt}\n{feedback_instruction}\n\n"
            f"Your available specialists are:\n{tools_list_str}"
        )
        router_instance.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=CoreSpecialist.ROUTER.value,
            system_prompt=dynamic_system_prompt
        )
        logger.info("RouterSpecialist adapter re-initialized with dynamic, context-aware prompt.")

    def _build_graph(self) -> StateGraph:
        # This method is correct and remains unchanged.
        workflow = StateGraph(GraphState)
        entry_point_node = CoreSpecialist.ROUTER.value
        for name, instance in self.specialists.items():
            workflow.add_node(name, instance.execute)
        workflow.set_entry_point(entry_point_node)
        conditional_map = {name: name for name in self.specialists if name != CoreSpecialist.ROUTER.value} # Map all specialists to themselves
        conditional_map[END] = END # If the router decides to END, go to the graph's END
        workflow.add_conditional_edges(entry_point_node, self.decide_next_specialist, conditional_map)
        for name in self.specialists:
            if name not in [CoreSpecialist.ROUTER.value, CoreSpecialist.ARCHIVER.value]:
                workflow.add_edge(name, CoreSpecialist.ROUTER.value)
        workflow.add_edge(CoreSpecialist.ARCHIVER.value, END)
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

        # Check for infinite loops. This check is now for observation;
        # the actual termination is handled by the router node's state update.
        turn_count = state.get("turn_count", 0)
        if turn_count >= MAX_TURNS:
            logger.error(f"Maximum turn limit of {MAX_TURNS} reached. Halting workflow.")
            return END

        next_specialist = state.get("next_specialist")
        logger.info(f"Router has selected next specialist: {next_specialist}")

        if next_specialist is None:
            logger.error("Routing Error: The router failed to select a next step. Halting workflow.")
            return END
        
        return next_specialist

    def get_graph(self) -> StateGraph:
        return self.graph
