# src/enums.py

from enum import Enum

class Specialist(Enum):
    """
    An enumeration of all specialist agents in the graph.
    The value of each member is the string identifier used by LangGraph.
    """
    ROUTER = "router_specialist"
    PROMPT = "prompt_specialist"
    DATA_EXTRACTOR = "data_extractor_specialist"
    FILE = "file_specialist"
