# src/enums.py

from enum import Enum

class CoreSpecialist(str, Enum):
    """
    An enumeration for core specialists with special, hardcoded roles in the graph.
    This is not a list of all specialists, but rather canonical names for roles
    that the orchestration logic depends on.
    """
    ROUTER = "router_specialist"
    TRIAGE = "prompt_triage_specialist"
    ARCHIVER = "archiver_specialist"
    PROMPT = "prompt_specialist"
    WEB_BUILDER = "web_builder"
    SYSTEMS_ARCHITECT = "systems_architect"
    CRITIC = "critic_specialist"
    DEFAULT_RESPONDER = "default_responder_specialist"
    END = "end_specialist"
    TRIAGE_ARCHITECT = "triage_architect"
    DIALOGUE = "dialogue_specialist"  # ADR-CORE-018: HitL clarification
    WEB = "web_specialist" # Deep Research Primitive