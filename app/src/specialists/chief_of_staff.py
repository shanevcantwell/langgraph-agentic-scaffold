import logging
import operator
from typing import Annotated, TypedDict, List

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END

from .systems_architect import SystemsArchitect
from .web_builder import WebBuilder
from ..graph.state import GraphState # Import the shared GraphState

logger = logging.getLogger(__name__)

class ChiefOfStaffSpecialist:
    """
    A standalone orchestrator class that manages an internal LangGraph to
    execute a sequence of tasks. It does NOT inherit from BaseSpecialist.
    """

    def __init__(self, systems_architect: SystemsArchitect, web_builder: WebBuilder):
        """
        Standard Python constructor for the orchestrator.
        """
        self.systems_architect = systems_architect
        self.web_builder = web_builder
        self.graph = self.compile_graph()

    def call_systems_architect(self, state: GraphState) -> dict:
        """Node that invokes the Systems Architect to generate a Mermaid diagram."""
        logger.info("CHIEF OF STAFF: Calling Systems Architect")
        try:
            return self.systems_architect.execute(state)
        except Exception as e:
            logger.error(f"Systems Architect failed: {e}")
            return {"error": f"Systems Architect failed: {e}"}

    def call_web_builder(self, state: GraphState) -> dict:
        """Node that invokes the Web Builder to create an HTML artifact."""
        logger.info("CHIEF OF STAFF: Calling Web Builder")
        if state.get("error"):
            return {}
        try:
            return self.web_builder.execute(state)
        except Exception as e:
            logger.error(f"Web Builder failed: {e}")
            return {"error": f"Web Builder failed: {e}"}

    def compile_graph(self) -> StateGraph:
        """
        Compiles the internal workflow graph for the Chief of Staff.
        """
        workflow = StateGraph(GraphState)
        workflow.add_node("systems_architect", self.call_systems_architect)
        workflow.add_node("web_builder", self.call_web_builder)
        workflow.set_entry_point("systems_architect")
        workflow.add_edge("systems_architect", "web_builder")
        workflow.add_edge("web_builder", END)
        return workflow.compile()

    def invoke(self, goal: str) -> dict:
        """
        Invokes the Chief of Staff's internal workflow with a high-level goal.
        """
        logger.info(f"CHIEF OF STAFF: Workflow initiated with goal: '{goal}'")
        initial_state = {"messages": [HumanMessage(content=goal)]}
        final_state = self.graph.invoke(initial_state)
        logger.info("CHIEF OF STAFF: Workflow Complete")
        return final_state