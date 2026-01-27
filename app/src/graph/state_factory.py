# app/src/graph/state_factory.py
"""
State initialization factory for creating properly structured GraphState objects.

This module eliminates state initialization duplication across runner.py and test files,
creating a single source of truth for the GraphState structure.

Refactoring: Priority 1 from Task 2.7 post-purge cleanup
"""
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage, BaseMessage

from app.src.graph.state import GraphState


def create_initial_state(
    goal: str,
    *,
    user_name: str = "user",
    text_to_process: Optional[str] = None,
    image_to_process: Optional[str] = None,
    use_simple_chat: bool = False,
    additional_artifacts: Optional[Dict[str, Any]] = None,
    additional_scratchpad: Optional[Dict[str, Any]] = None,
    distillation_state: Optional[Dict[str, Any]] = None,
) -> GraphState:
    """
    Creates a properly initialized GraphState dictionary.

    This factory function encapsulates the canonical pattern for state initialization,
    ensuring consistency across runner.py and all test files.

    Args:
        goal: The user's initial message content
        user_name: Name attribute for the HumanMessage (default: "user")
        text_to_process: Optional text content to add to artifacts
        image_to_process: Optional base64 image to add to artifacts
        use_simple_chat: Whether to use simple chat mode (added to scratchpad)
        additional_artifacts: Optional dict to merge into artifacts
        additional_scratchpad: Optional dict to merge into scratchpad
        distillation_state: Optional distillation workflow state

    Returns:
        GraphState: Properly structured initial state dictionary

    Example:
        >>> state = create_initial_state("What is the capital of France?")
        >>> state = create_initial_state(
        ...     "Analyze this text",
        ...     text_to_process="Lorem ipsum...",
        ...     use_simple_chat=True
        ... )
    """
    # Build core state structure
    initial_state: GraphState = {
        "messages": [HumanMessage(content=goal, name=user_name)],
        "routing_history": [],
        "turn_count": 0,
        "task_is_complete": False,
        "next_specialist": None,
        "artifacts": {},
        "scratchpad": {},
    }

    # Add distillation state if provided
    if distillation_state is not None:
        initial_state["distillation_state"] = distillation_state

    # Store verbatim user request for specialists (distinct from specialist-internal *_goal fields)
    initial_state["artifacts"]["user_request"] = goal

    # Populate artifacts
    if text_to_process:
        initial_state["artifacts"]["text_to_process"] = text_to_process

    if image_to_process:
        initial_state["artifacts"]["uploaded_image.png"] = image_to_process

    if additional_artifacts:
        initial_state["artifacts"].update(additional_artifacts)

    # Populate scratchpad
    if use_simple_chat:
        initial_state["scratchpad"]["use_simple_chat"] = use_simple_chat

    if additional_scratchpad:
        initial_state["scratchpad"].update(additional_scratchpad)

    return initial_state


def create_test_state(
    messages: Optional[list[BaseMessage]] = None,
    *,
    turn_count: int = 0,
    task_is_complete: bool = False,
    next_specialist: Optional[str] = None,
    artifacts: Optional[Dict[str, Any]] = None,
    scratchpad: Optional[Dict[str, Any]] = None,
    routing_history: Optional[list[str]] = None,
    distillation_state: Optional[Dict[str, Any]] = None,
) -> GraphState:
    """
    Creates a GraphState for testing with explicit control over all fields.

    Unlike create_initial_state (which is designed for runtime workflows),
    this function allows tests to construct arbitrary state configurations
    without needing to provide a goal string.

    Args:
        messages: List of BaseMessage objects (default: empty list)
        turn_count: Current turn count
        task_is_complete: Whether task is marked complete
        next_specialist: Name of next specialist to route to
        artifacts: Artifacts dictionary
        scratchpad: Scratchpad dictionary
        routing_history: List of routing entries
        distillation_state: Optional distillation workflow state

    Returns:
        GraphState: Properly structured test state dictionary

    Example:
        >>> state = create_test_state(
        ...     messages=[HumanMessage(content="Test")],
        ...     artifacts={"test_artifact": "value"},
        ...     scratchpad={"error_report": "Test error"}
        ... )
    """
    return {
        "messages": messages or [],
        "routing_history": routing_history or [],
        "turn_count": turn_count,
        "task_is_complete": task_is_complete,
        "next_specialist": next_specialist,
        "artifacts": artifacts or {},
        "scratchpad": scratchpad or {},
        "distillation_state": distillation_state,
    }
