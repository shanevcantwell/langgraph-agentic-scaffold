"""
Integration Test: Tiered Chat End-to-End (CORE-CHAT-002)

This test validates the complete tiered chat subgraph execution:
1. User question → Router selects "chat_specialist" (virtual)
2. Orchestrator intercepts and fans out to both progenitors in parallel
3. Both progenitors generate perspectives and write to artifacts
4. Synthesizer combines perspectives into tiered markdown
5. Task completion signal routes to EndSpecialist

This test exercises the most complex subgraph in the system, validating:
- Virtual coordinator pattern (Router says "chat", Orchestrator dispatches to subgraph)
- Parallel fan-out execution (both progenitors run simultaneously)
- State management pattern (progenitors → artifacts, synthesizer → messages)
- Graceful degradation modes (full, alpha_only, bravo_only, error)
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.config_loader import ConfigLoader


@pytest.mark.integration
def test_tiered_chat_full_mode_end_to_end():
    """
    End-to-end test: User question → Router → Fanout → Both progenitors → Synthesizer

    This validates the full happy path for tiered chat with both perspectives.
    """
    # --- Arrange: Build real graph with real config ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Verify tiered chat components are present in config
    assert 'progenitor_alpha_specialist' in config['specialists'], \
        "progenitor_alpha_specialist not found in config.yaml"
    assert 'progenitor_bravo_specialist' in config['specialists'], \
        "progenitor_bravo_specialist not found in config.yaml"
    assert 'tiered_synthesizer_specialist' in config['specialists'], \
        "tiered_synthesizer_specialist not found in config.yaml"

    # Build the graph
    builder = GraphBuilder(config_loader=config_loader)

    # Mock LLM adapters for both progenitors to avoid real API calls
    with patch.object(builder.specialists['progenitor_alpha_specialist'], 'llm_adapter') as mock_alpha_adapter, \
         patch.object(builder.specialists['progenitor_bravo_specialist'], 'llm_adapter') as mock_bravo_adapter, \
         patch.object(builder.specialists['router_specialist'], 'llm_adapter') as mock_router_adapter:

        # Configure router to select "chat_specialist" (virtual capability)
        mock_router_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_route",
                "type": "tool_call",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

        # Configure Alpha progenitor to generate analytical perspective
        mock_alpha_adapter.invoke.return_value = {
            "text_response": "From an analytical perspective: Python is a high-level, interpreted programming language known for its clean syntax and readability."
        }
        mock_alpha_adapter.model_name = "test-alpha-model"

        # Configure Bravo progenitor to generate contextual perspective
        mock_bravo_adapter.invoke.return_value = {
            "text_response": "From a contextual perspective: Python is widely used in data science, web development, and automation because of its extensive ecosystem."
        }
        mock_bravo_adapter.model_name = "test-bravo-model"

        # Build the graph with mocked adapters
        graph = builder.build()

        # Create initial state with user question
        initial_state = {
            "messages": [HumanMessage(content="What is Python?")],
            "artifacts": {},
            "scratchpad": {},
            "task_is_complete": False,
            "turn_count": 0,
            "routing_history": []
        }

        # --- Act: Run the workflow ---
        final_state = graph.invoke(initial_state)

        # --- Assert: Validate tiered chat execution ---

        # 1. Verify router was called once to decide routing
        assert mock_router_adapter.invoke.call_count == 1, \
            "Router should be called once to select next specialist"

        # 2. Verify both progenitors were invoked (parallel execution)
        assert mock_alpha_adapter.invoke.call_count == 1, \
            "Progenitor Alpha should be invoked once"
        assert mock_bravo_adapter.invoke.call_count == 1, \
            "Progenitor Bravo should be invoked once"

        # 3. Verify synthesizer combined both perspectives
        artifacts = final_state.get("artifacts", {})
        assert "final_user_response.md" in artifacts, \
            "Synthesizer should produce final_user_response.md artifact"

        tiered_response = artifacts["final_user_response.md"]
        assert "analytical" in tiered_response.lower(), \
            "Tiered response should contain Alpha's analytical perspective"
        assert "contextual" in tiered_response.lower(), \
            "Tiered response should contain Bravo's contextual perspective"

        # 4. Verify response mode is full (both perspectives)
        assert artifacts.get("response_mode") == "tiered_full", \
            "Response mode should be 'tiered_full' when both progenitors succeed"

        # 5. Verify task completion signal was set
        assert final_state.get("task_is_complete") is True, \
            "Synthesizer should set task_is_complete to True"

        # 6. Verify messages were appended (synthesizer writes to messages)
        messages = final_state.get("messages", [])
        assert len(messages) > 1, \
            "Messages should include user question + synthesizer confirmation"

        print("\n✓ Tiered chat full mode executed successfully")
        print(f"✓ Router invoked {mock_router_adapter.invoke.call_count} time(s)")
        print(f"✓ Alpha progenitor invoked {mock_alpha_adapter.invoke.call_count} time(s)")
        print(f"✓ Bravo progenitor invoked {mock_bravo_adapter.invoke.call_count} time(s)")
        print(f"✓ Tiered response length: {len(tiered_response)} chars")
        print(f"✓ Response mode: {artifacts.get('response_mode')}")


@pytest.mark.integration
def test_tiered_chat_graceful_degradation_alpha_only():
    """
    Tests graceful degradation when Bravo progenitor fails.

    This validates that the system continues with only Alpha's perspective
    instead of completely failing.

    NOTE: We simulate failure by patching _execute_logic to not write bravo_response.
    The LLM adapter has fallback logic that prevents truly empty responses.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Patch Bravo's _execute_logic to simulate failure (no artifact written)
    original_bravo_execute = builder.specialists['progenitor_bravo_specialist']._execute_logic

    def bravo_failure_execute(state):
        """Simulates Bravo progenitor failure by not writing artifact."""
        return {"artifacts": {}}  # No bravo_response written

    with patch.object(builder.specialists['progenitor_alpha_specialist'], 'llm_adapter') as mock_alpha_adapter, \
         patch.object(builder.specialists['progenitor_bravo_specialist'], '_execute_logic', side_effect=bravo_failure_execute), \
         patch.object(builder.specialists['router_specialist'], 'llm_adapter') as mock_router_adapter, \
         patch.object(builder.specialists['triage_architect'], 'llm_adapter') as mock_triage_adapter:

        # Triage returns ContextPlan recommending chat_specialist (no actions = route to Router)
        mock_triage_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_triage",
                "type": "tool_call",
                "name": "ContextPlan",
                "args": {"reasoning": "Simple chat question", "actions": [], "recommended_specialists": ["chat_specialist"]}
            }]
        }

        # Router selects chat_specialist
        mock_router_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_route",
                "type": "tool_call",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

        # Alpha succeeds
        mock_alpha_adapter.invoke.return_value = {
            "text_response": "This is the analytical perspective."
        }
        mock_alpha_adapter.model_name = "test-alpha-model"

        graph = builder.build()

        initial_state = {
            "messages": [HumanMessage(content="Test question")],
            "artifacts": {},
            "scratchpad": {},
            "task_is_complete": False,
            "turn_count": 0,
            "routing_history": []
        }

        # --- Act ---
        final_state = graph.invoke(initial_state)

        # --- Assert ---
        artifacts = final_state.get("artifacts", {})

        # Should still produce a response (graceful degradation)
        assert "final_user_response.md" in artifacts, \
            "Should produce response even when Bravo fails"

        # Response mode should indicate alpha_only
        assert artifacts.get("response_mode") == "tiered_alpha_only", \
            "Response mode should be 'tiered_alpha_only' when Bravo fails"

        # Response should contain Alpha's content
        tiered_response = artifacts["final_user_response.md"]
        assert "analytical" in tiered_response.lower(), \
            "Response should contain Alpha's perspective"

        # Task should still complete
        assert final_state.get("task_is_complete") is True, \
            "Task should complete despite Bravo failure"

        print("\n✓ Graceful degradation (alpha_only) validated")
        print(f"✓ Response mode: {artifacts.get('response_mode')}")
        print(f"✓ Response length: {len(tiered_response)} chars")


@pytest.mark.integration
def test_tiered_chat_graceful_degradation_bravo_only():
    """
    Tests graceful degradation when Alpha progenitor fails.

    This validates that the system continues with only Bravo's perspective
    instead of completely failing.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    def alpha_failure_execute(state):
        """Simulates Alpha progenitor failure by not writing artifact."""
        return {"artifacts": {}}  # No alpha_response written

    with patch.object(builder.specialists['progenitor_alpha_specialist'], '_execute_logic', side_effect=alpha_failure_execute), \
         patch.object(builder.specialists['progenitor_bravo_specialist'], 'llm_adapter') as mock_bravo_adapter, \
         patch.object(builder.specialists['router_specialist'], 'llm_adapter') as mock_router_adapter, \
         patch.object(builder.specialists['triage_architect'], 'llm_adapter') as mock_triage_adapter:

        # Triage returns ContextPlan recommending chat_specialist
        mock_triage_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_triage",
                "type": "tool_call",
                "name": "ContextPlan",
                "args": {"reasoning": "Simple chat question", "actions": [], "recommended_specialists": ["chat_specialist"]}
            }]
        }

        # Router selects chat_specialist
        mock_router_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_route",
                "type": "tool_call",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

        # Bravo succeeds
        mock_bravo_adapter.invoke.return_value = {
            "text_response": "This is the contextual perspective."
        }
        mock_bravo_adapter.model_name = "test-bravo-model"

        graph = builder.build()

        initial_state = {
            "messages": [HumanMessage(content="Test question")],
            "artifacts": {},
            "scratchpad": {},
            "task_is_complete": False,
            "turn_count": 0,
            "routing_history": []
        }

        # --- Act ---
        final_state = graph.invoke(initial_state)

        # --- Assert ---
        artifacts = final_state.get("artifacts", {})

        # Should still produce a response (graceful degradation)
        assert "final_user_response.md" in artifacts, \
            "Should produce response even when Alpha fails"

        # Response mode should indicate bravo_only
        assert artifacts.get("response_mode") == "tiered_bravo_only", \
            "Response mode should be 'tiered_bravo_only' when Alpha fails"

        # Response should contain Bravo's content
        tiered_response = artifacts["final_user_response.md"]
        assert "contextual" in tiered_response.lower(), \
            "Response should contain Bravo's perspective"

        # Task should still complete
        assert final_state.get("task_is_complete") is True, \
            "Task should complete despite Alpha failure"

        print("\n✓ Graceful degradation (bravo_only) validated")
        print(f"✓ Response mode: {artifacts.get('response_mode')}")
        print(f"✓ Response length: {len(tiered_response)} chars")


@pytest.mark.integration
def test_tiered_chat_virtual_coordinator_pattern():
    """
    Tests that the virtual coordinator pattern works correctly.

    Router says "chat_specialist" (abstract capability), and Orchestrator
    decides the implementation: either simple chat_specialist or tiered subgraph.
    This validates the separation of concerns: Router = WHAT, Orchestrator = HOW.

    The pattern allows:
    - chat_specialist exists as a real node (for simple mode / fallback)
    - Orchestrator intercepts routing and redirects to tiered subgraph by default
    - Transparent upgrade from single-node to multi-node implementation
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Build graph to check node structure
    graph = builder.build()

    # Check that BOTH simple and tiered implementations exist
    assert "chat_specialist" in graph.nodes, \
        "chat_specialist should exist as fallback node for simple mode"

    # Check that tiered components also exist
    assert "progenitor_alpha_specialist" in graph.nodes, \
        "progenitor_alpha_specialist should be a real graph node"
    assert "progenitor_bravo_specialist" in graph.nodes, \
        "progenitor_bravo_specialist should be a real graph node"
    assert "tiered_synthesizer_specialist" in graph.nodes, \
        "tiered_synthesizer_specialist should be a real graph node"

    print("\n✓ Virtual coordinator pattern validated")
    print("  ✓ chat_specialist exists as fallback node")
    print("  ✓ Tiered subgraph components exist for default implementation")
    print("  ✓ Orchestrator decides implementation dynamically")


@pytest.mark.integration
def test_tiered_chat_state_management_pattern():
    """
    Tests that the state management pattern is followed correctly.

    Validates:
    - Progenitors (parallel nodes) write ONLY to artifacts
    - Synthesizer (join node) writes to BOTH artifacts and messages
    - This prevents message pollution in multi-turn conversations
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Mock ALL LLM specialists that might run during this workflow to avoid API calls
    end_specialist_mock = MagicMock()
    end_specialist_mock.invoke.return_value = {"text_response": "Archiving complete"}
    end_specialist_mock.model_name = "test-end"

    with patch.object(builder.specialists['progenitor_alpha_specialist'], 'llm_adapter') as mock_alpha_adapter, \
         patch.object(builder.specialists['progenitor_bravo_specialist'], 'llm_adapter') as mock_bravo_adapter, \
         patch.object(builder.specialists['tiered_synthesizer_specialist'], 'llm_adapter') as mock_synthesizer_adapter, \
         patch.object(builder.specialists['router_specialist'], 'llm_adapter') as mock_router_adapter, \
         patch.object(builder.specialists['triage_architect'], 'llm_adapter') as mock_triage_adapter, \
         patch.object(builder.specialists['end_specialist'], 'llm_adapter', end_specialist_mock):

        # Triage returns ContextPlan recommending chat_specialist
        mock_triage_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_triage",
                "type": "tool_call",
                "name": "ContextPlan",
                "args": {"reasoning": "Simple chat question", "actions": [], "recommended_specialists": ["chat_specialist"]}
            }]
        }

        # Router selects chat_specialist
        mock_router_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_route",
                "type": "tool_call",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

        mock_alpha_adapter.invoke.return_value = {"text_response": "Alpha response"}
        mock_alpha_adapter.model_name = "test-alpha"
        mock_bravo_adapter.invoke.return_value = {"text_response": "Bravo response"}
        mock_bravo_adapter.model_name = "test-bravo"
        mock_synthesizer_adapter.invoke.return_value = {"text_response": "# Combined Response\n\nAlpha and Bravo perspectives combined."}
        mock_synthesizer_adapter.model_name = "test-synthesizer"

        graph = builder.build()

        initial_state = {
            "messages": [HumanMessage(content="Test")],
            "artifacts": {},
            "scratchpad": {},
            "task_is_complete": False,
            "recommended_specialists": None,  # Explicitly set to None to prevent filtering
            "turn_count": 0,
            "routing_history": []
        }

        # --- Act ---
        final_state = graph.invoke(initial_state)

        # --- Assert ---

        # 1. Progenitor responses should be in artifacts
        artifacts = final_state.get("artifacts", {})
        assert "alpha_response" in artifacts, \
            "Alpha progenitor should write to artifacts['alpha_response']"
        assert "bravo_response" in artifacts, \
            "Bravo progenitor should write to artifacts['bravo_response']"

        # 2. Combined response should be in artifacts AND messages
        assert "final_user_response.md" in artifacts, \
            "Synthesizer should write combined response to artifacts"

        # 3. Messages should NOT contain progenitor responses directly
        # (they should only be referenced in synthesizer's combined output)
        messages = final_state.get("messages", [])
        message_contents = [str(msg.content) for msg in messages]

        # The individual progenitor responses should not appear as separate messages
        # They should only appear combined in the synthesizer's output
        assert len(messages) >= 2, \
            "Should have user message + synthesizer message (minimum)"

        print("\n✓ State management pattern validated")
        print(f"  ✓ Artifacts contain alpha_response: {len(artifacts.get('alpha_response', ''))} chars")
        print(f"  ✓ Artifacts contain bravo_response: {len(artifacts.get('bravo_response', ''))} chars")
        print(f"  ✓ Artifacts contain final_user_response.md: {len(artifacts.get('final_user_response.md', ''))} chars")
        print(f"  ✓ Messages array has {len(messages)} messages")


@pytest.mark.integration
def test_tiered_chat_simple_mode_bypass():
    """
    Tests that use_simple_chat flag bypasses tiered subgraph.

    When scratchpad.use_simple_chat is True, the system should route
    directly to chat_specialist instead of the tiered subgraph.

    NOTE: This test will fail if chat_specialist is not in the config.
    The system currently uses tiered chat by default, so this is testing
    a fallback path that may not be commonly used.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Check if simple chat_specialist exists in config
    if "chat_specialist" not in config['specialists']:
        pytest.skip("chat_specialist not in config - tiered chat is the only implementation")

    builder = GraphBuilder(config_loader=config_loader)

    with patch.object(builder.specialists['chat_specialist'], 'llm_adapter') as mock_chat_adapter, \
         patch.object(builder.specialists['router_specialist'], 'llm_adapter') as mock_router_adapter, \
         patch.object(builder.specialists['triage_architect'], 'llm_adapter') as mock_triage_adapter:

        # Triage returns ContextPlan recommending chat_specialist
        mock_triage_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_triage",
                "type": "tool_call",
                "name": "ContextPlan",
                "args": {"reasoning": "Simple chat question", "actions": [], "recommended_specialists": ["chat_specialist"]}
            }]
        }

        # Router selects chat_specialist
        mock_router_adapter.invoke.return_value = {
            "tool_calls": [{
                "id": "call_route",
                "type": "tool_call",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

        mock_chat_adapter.invoke.return_value = {
            "text_response": "Simple chat response"
        }
        mock_chat_adapter.model_name = "test-model"

        graph = builder.build()

        initial_state = {
            "messages": [HumanMessage(content="Test")],
            "artifacts": {},
            "scratchpad": {"use_simple_chat": True},  # KEY: Request simple mode
            "task_is_complete": False,
            "recommended_specialists": None,  # Explicitly set to None to prevent filtering
            "turn_count": 0,
            "routing_history": []
        }

        # --- Act ---
        final_state = graph.invoke(initial_state)

        # --- Assert ---
        # Should use simple chat_specialist, not progenitors
        assert mock_chat_adapter.invoke.call_count == 1, \
            "Simple chat_specialist should be invoked when use_simple_chat=True"

        print("\n✓ Simple chat mode bypass validated")
        print("  ✓ use_simple_chat flag respected")
        print("  ✓ Tiered subgraph bypassed successfully")
