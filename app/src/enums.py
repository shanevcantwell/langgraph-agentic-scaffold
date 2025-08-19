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
    DATA_PROCESSOR = "data_processor_specialist" # New specialist
    FILE = "file_specialist"
    SYSTEMS_ARCHITECT = "systems_architect"
    WEB_BUILDER = "web_builder"

class Edge(Enum):
    """
    An enumeration of all edge names in the graph.
    """
    CONTINUE = "continue"
    END = "__end__"
