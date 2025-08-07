# src/enums.py

from enum import Enum

class Specialist(Enum):
    """
    An enumeration of all specialist agents in the graph.
    The value of each member is the string identifier used by LangGraph.
    """
    HELLO_WORLD = "hello_world_specialist"
    # Add new specialists here, e.g.:
    # GOODBYE_WORLD = "goodbye_world_specialist"
