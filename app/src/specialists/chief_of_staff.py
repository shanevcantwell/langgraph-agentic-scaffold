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

    # Add this inside the ChiefOfStaff class in chief_of_staff.py

    def decide_next_step(self, state: GraphState) -> str:
        """Decides the next step based on whether an error is present in the state."""
        logger.info("CHIEF OF STAFF: Checking for errors to decide next step.")
        if "error" in state and state["error"]:
            logger.error(f"CHIEF OF STAFF: Error detected. Halting workflow. Details: {state.get('error_details')}")
            return "__end__"  # A special key indicating the end of the graph
        logger.info("CHIEF OF STAFF: No errors found. Proceeding to Web Builder.")
        return "call_web_builder"

    def call_systems_architect(self, state: GraphState) -> dict:
        """Node that invokes the Systems Architect to generate a Mermaid diagram."""
        logger.info("CHIEF OF STAFF: Calling Systems Architect")
        result = self.systems_architect.execute(state)
        if result.get("error"):
            logger.error(f"Systems Architect failed: {result['error']}")
            return result # Propagate the error and error_details
        return result

    def call_web_builder(self, state: GraphState) -> dict:
        """Node that invokes the Web Builder to create an HTML artifact."""
        logger.info("CHIEF OF STAFF: Calling Web Builder")
        if state.get("error"): # Check if there's an existing error from a previous step
            return state # Propagate the existing error
        
        result = self.web_builder.execute(state)
        if result.get("error"):
            logger.error(f"Web Builder failed: {result['error']}")
            return result # Propagate the error and error_details
        return result

    def compile_graph(self) -> StateGraph:
        """
        Compiles the internal workflow graph for the Chief of Staff.
        """
        workflow = StateGraph(GraphState)
        workflow.add_node("systems_architect", self.call_systems_architect)
        workflow.add_node("web_builder", self.call_web_builder)
        
        workflow.set_entry_point("systems_architect")
        
        # This is the new conditional logic
        workflow.add_conditional_edges(
            "systems_architect",
            self.decide_next_step,
            {
                "call_web_builder": "web_builder",
                "__end__": END
            }
        )
        
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
        
        if final_state.get("error"):
            error_message = final_state["error"]
            error_details = final_state.get("error_details", "No detailed error information available.")
            return {"status": "error", "message": error_message, "details": error_details}
        else:
            return {"status": "success", "final_state": final_state}