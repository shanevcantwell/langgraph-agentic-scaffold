# src/enums.py

from enum import Enum
from langgraph.graph import END as LANGGRAPH_END

class Edge(Enum):
    """
    An enumeration for standard graph edge names.
    NOTE: The Specialist enum was removed as it was a static list that conflicted
    with the system's dynamic, configuration-driven specialist loading.
    The router_specialist now generates the list of specialists dynamically.
    """
    END = LANGGRAPH_END