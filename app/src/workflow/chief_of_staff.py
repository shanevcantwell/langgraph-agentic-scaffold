import logging
from typing import Dict

from langgraph.graph import StateGraph, END

from ..graph.state import GraphState
from ..specialists import get_specialist_class
from ..utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

class ChiefOfStaff:
    """
    The Chief of Staff is the master orchestrator for the multi-agent system.
    It is responsible for compiling the final, runnable LangGraph application
    by wiring together all the specialists and defining the workflow logic.
    """

    def __init__(self):
        """
        Initializes the ChiefOfStaff, loading specialists defined in the configuration.
        """
        self.config = ConfigLoader().get_config()
        self.specialists = self._load_specialists()

    def _load_specialists(self) -> Dict[str, any]:
        """Dynamically load and instantiate specialists from config."""
        specialist_instances = {}
        specialist_configs = self.config.get("specialists", {})
        for name in specialist_configs:
            try:
                SpecialistClass = get_specialist_class(name)
                specialist_instances[name] = SpecialistClass()
                logger.info(f"Successfully instantiated specialist: {name}")
            except (ImportError, AttributeError) as e:
                logger.error(f"Could not load specialist '{name}': {e}")
        return specialist_instances

    def compile_graph(self):
        """
        Compiles and returns the LangGraph application.
        This method dynamically builds the graph based on the loaded specialists.
        """
        workflow = StateGraph(GraphState)

        # Dynamically add all loaded specialists as nodes
        for name, instance in self.specialists.items():
            workflow.add_node(name, instance.execute)

        # The entry point must be the router specialist
        router_name = "router_specialist"
        if router_name not in self.specialists:
            raise ValueError(f"Configuration must include a '{router_name}'.")
        workflow.set_entry_point(router_name)

        def decide_next_specialist(state: GraphState) -> str:
            """Inspects the state to decide which specialist to route to next."""
            logger.info("---ROUTING DECISION---")
            if state.get("error"):
                logger.error(f"Error detected: {state['error']}. Ending workflow.")
                return END

            next_specialist = state.get("next_specialist")
            if not next_specialist:
                logger.warning("No next specialist decided. Defaulting to end.")
                return END

            logger.info(f"Routing to: {next_specialist}")
            return next_specialist

        # Create a dynamic mapping for conditional edges from the router
        # to all other specialists.
        specialist_nodes = [name for name in self.specialists if name != router_name]
        routing_map = {name: name for name in specialist_nodes}
        routing_map[END] = END

        workflow.add_conditional_edges(
            router_name,
            decide_next_specialist,
            routing_map
        )

        # After any specialist runs, it returns control to the router.
        for specialist_name in specialist_nodes:
            workflow.add_edge(specialist_name, router_name)

        app = workflow.compile()
        logger.info("---ChiefOfStaff: Graph compiled successfully.---")
        return app
