# src/graph/nodes.py

from .state import GraphState
from ..enums import Specialist # <-- Import the enum

def router(state: GraphState) -> str:
    """
    This node is responsible for routing to the correct specialist
    based on the current state.

    For now, it's hardcoded to always route to the hello_world_specialist.

    Args:
        state: The current state of the graph.

    Returns:
        A string key that corresponds to the next node to call.
    """
    print("---ROUTING---")
    # In a real router, you would have logic to inspect the state
    # and decide which specialist to call next.
    return Specialist.HELLO_WORLD.value # <-- Use the enum value

