import logging
from typing import Dict, Any

from langgraph.graph import StateGraph, END

from ..graph.state import GraphState
from ..specialists.systems_architect import SystemsArchitect
from ..specialists.web_builder import WebBuilder
from ..specialists.router_specialist import RouterSpecialist
from ..specialists.prompt_specialist import PromptSpecialist

logger = logging.getLogger(__name__)

class ChiefOfStaff:
    """
    The Chief of Staff is the master orchestrator for the multi-agent system.
    It is responsible for compiling the final, runnable LangGraph application
    by wiring together all the specialists and defining the workflow logic.
    """

    def __init__(self):
        """
        Initializes the ChiefOfStaff and all the specialists it manages.
        """
        self.router = RouterSpecialist()
        self.systems_architect = SystemsArchitect()
        self.web_builder = WebBuilder()
        self.prompt_specialist = PromptSpecialist()

    def compile_graph(self):
        """
        Compiles and returns the LangGraph application.
        This defines the nodes and the conditional edges of the workflow.
        """
        workflow = StateGraph(GraphState)

        # Add nodes for each specialist
        workflow.add_node("router", self.router.execute)
        workflow.add_node("systems_architect", self.systems_architect.execute)
        workflow.add_node("web_builder", self.web_builder.execute)
        workflow.add_node("prompt_specialist", self.prompt_specialist.execute)

        workflow.set_entry_point("router")

        def decide_next_specialist(state: GraphState) -> str:
            """
            Inspects the state to decide which specialist to route to next.
            """
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

        workflow.add_conditional_edges(
            "router",
            decide_next_specialist,
            {
                "systems_architect": "systems_architect",
                "prompt_specialist": "prompt_specialist",
                END: END
            }
        )

        workflow.add_edge("systems_architect", "web_builder")
        
        workflow.add_edge("web_builder", END)
        workflow.add_edge("prompt_specialist", END)

        app = workflow.compile()
        logger.info("---ChiefOfStaff: Graph compiled successfully.---")
        return app
