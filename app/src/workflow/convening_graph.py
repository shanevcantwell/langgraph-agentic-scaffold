import logging
from typing import TypedDict, List, Optional, Annotated, Dict, Any
import operator

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage

from ..specialists.tribe_conductor import TribeConductor
from ..specialists.progenitor_alpha_specialist import ProgenitorAlphaSpecialist
from ..specialists.progenitor_bravo_specialist import ProgenitorBravoSpecialist
# Import other specialists as needed

logger = logging.getLogger(__name__)

class ConveningState(TypedDict):
    """
    State schema for the Convening of the Tribes architecture (ADR-CORE-023).
    """
    # Core LangGraph state
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Convening-specific state
    manifest_path: str
    active_branch_id: Optional[str]
    
    # Orchestration flags
    fishbowl_active: bool
    synthesis_pending: bool
    hitl_required: bool
    
    # Scratchpad for inter-node communication
    scratchpad: Dict[str, Any]
    
    # Artifacts (The Heap pointers, etc.)
    artifacts: Dict[str, Any]


class ConveningGraphBuilder:
    """
    Builds the Convening StateGraph.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # Initialize specialists
        # Note: In a real implementation, these would be injected or loaded via factory
        self.conductor = TribeConductor("tribe_conductor", config)
        # self.alpha = ProgenitorAlphaSpecialist(...)
        # self.bravo = ProgenitorBravoSpecialist(...)

    def build(self) -> StateGraph:
        workflow = StateGraph(ConveningState)

        # Add Nodes
        workflow.add_node("tribe_conductor", self.conductor.execute)
        
        # Placeholder nodes for other specialists
        # workflow.add_node("progenitor_alpha", self.alpha.execute)
        # workflow.add_node("progenitor_bravo", self.bravo.execute)

        # Set Entry Point
        workflow.set_entry_point("tribe_conductor")

        # Add Conditional Edges from Conductor
        workflow.add_conditional_edges(
            "tribe_conductor",
            self._route_from_conductor,
            {
                "progenitor_alpha_specialist": END, # Placeholder: Should route to actual node
                "progenitor_bravo_specialist": END,
                "project_director": END,
                "dialogue_specialist": END,
                "triage_architect": END,
                "end": END
            }
        )

        return workflow

    def _route_from_conductor(self, state: ConveningState) -> str:
        """
        Determine the next node based on the conductor's scratchpad output.
        """
        scratchpad = state.get("scratchpad", {})
        next_specialist = scratchpad.get("next_specialist")
        
        if next_specialist:
            return next_specialist
            
        return "end"
