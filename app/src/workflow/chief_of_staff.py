import logging
from typing import Dict
from langgraph.graph import StateGraph, END

from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt
from ..specialists import get_specialist_class, BaseSpecialist
from ..graph.state import GraphState
from ..llm.factory import AdapterFactory

logger = logging.getLogger(__name__)

class ChiefOfStaff:
    """
    The ChiefOfStaff is the central orchestrator. It is responsible for:
    1. Loading all specialists from the configuration.
    2. Conducting the "morning standup" to make the router aware of its peers.
    3. Building and compiling the LangGraph workflow.
    """
    def __init__(self):
        self.config = ConfigLoader().get_config()
        self.specialists = self._load_and_configure_specialists()
        self.graph = self._build_graph()
        logger.info("---ChiefOfStaff: Graph compiled successfully.---")

    def _load_and_configure_specialists(self) -> Dict[str, BaseSpecialist]:
        """
        Loads all specialists defined in the config, then performs a 'morning standup'
        to provide the router with context about its peers.
        """
        specialists_config = self.config.get("specialists", {})
        loaded_specialists: Dict[str, BaseSpecialist] = {}

        # First pass: Instantiate all specialists
        for name, config in specialists_config.items():
            try:
                SpecialistClass = get_specialist_class(name, config)
                instance = SpecialistClass()
                loaded_specialists[name] = instance
                logger.info(f"Successfully instantiated specialist: {name}")
            except Exception as e:
                logger.error(f"Failed to instantiate specialist '{name}': {e}", exc_info=True)
                raise

        # Second pass: The "Morning Standup" - configure the router
        if "router_specialist" in loaded_specialists:
            self._configure_router(loaded_specialists, specialists_config)
        
        return loaded_specialists

    def _configure_router(self, specialists: Dict[str, BaseSpecialist], configs: Dict):
        """Injects a context-aware LLM adapter into the router specialist."""
        logger.info("Conducting 'morning standup' to configure the router...")
        router_instance = specialists["router_specialist"]
        router_config = configs.get("router_specialist", {})

        # Build the dynamic part of the prompt from peer descriptions
        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in configs.items() if name != "router_specialist"]
        tools_list_str = "\n".join(available_tools_desc)

        # Load the router's base prompt from its configured file
        base_prompt_file = router_config.get("prompt_file")
        base_prompt = load_prompt(base_prompt_file) if base_prompt_file else ""
        
        dynamic_system_prompt = f"{base_prompt}\n\nAVAILABLE SPECIALISTS:\n{tools_list_str}"

        # Create a new, context-aware adapter and inject it into the router instance
        router_instance.llm_adapter = AdapterFactory().create_adapter(
            specialist_name="router_specialist",
            system_prompt=dynamic_system_prompt
        )
        logger.info("RouterSpecialist adapter re-initialized with dynamic, context-aware prompt.")

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(GraphState)
        workflow.add_node("router", self.specialists["router_specialist"].execute)

        for name, instance in self.specialists.items():
            if name != "router_specialist":
                workflow.add_node(name, instance.execute)
        
        workflow.set_entry_point("router")
        workflow.add_conditional_edges("router", self.decide_next_specialist, {name: name for name in self.specialists if name != "router_specialist"} | {END: END})

        for name in self.specialists:
            if name != "router_specialist":
                workflow.add_edge(name, "router")

        return workflow.compile()

    def decide_next_specialist(self, state: GraphState) -> str:
        logger.info("---ROUTING DECISION---")
        if error := state.get("error"):
            logger.error(f"Error detected: {error}. Ending workflow.")
            return END
        next_specialist = state.get("next_specialist")
        logger.info(f"Routing to: {next_specialist}")
        return next_specialist if next_specialist else END

    def get_graph(self) -> StateGraph:
        return self.graph