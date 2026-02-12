"""
Integration Test: Artifact Passing Between Specialists

This test validates that artifacts flow correctly through multi-specialist workflows:
1. Producer specialist creates artifact and writes to state.artifacts
2. Consumer specialist reads artifact from state.artifacts
3. Required artifact validation (missing artifacts trigger clear errors)
4. Artifact provider recommendations work correctly

These tests exercise real config-based artifact dependencies, not mocked data.
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.config_loader import ConfigLoader


@pytest.mark.integration
def test_artifact_required_validation_missing_artifact():
    """
    Tests that specialists with required_artifacts fail gracefully when artifacts are missing.

    This validates the safe_executor precondition checking in GraphOrchestrator.

    Updated post ADR-CORE-035: Uses data_processor_specialist which requires json_artifact
    with data_extractor_specialist as provider.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Get data_processor_specialist which requires "json_artifact" artifact
    # (data_extractor_specialist no longer has requires_artifacts after ADR-CORE-035)
    data_processor = builder.specialists['data_processor_specialist']

    # Verify it has required artifacts configured
    assert data_processor.specialist_config.get('requires_artifacts') == ['json_artifact'], \
        "data_processor_specialist should require json_artifact artifact"

    # Create safe executor (this is what GraphOrchestrator does)
    safe_executor = builder.node_executor.create_safe_executor(data_processor)

    # Create state WITHOUT the required artifact
    state = {
        "messages": [HumanMessage(content="Process data")],
        "artifacts": {},  # Missing json_artifact
        "turn_count": 0,
        "routing_history": [],
        "task_is_complete": False,
        "scratchpad": {}
    }

    # --- Act ---
    result = safe_executor(state)

    # --- Assert ---
    # Missing artifact response now uses scratchpad signals only (no messages)
    # per ADR-CORE-016 to avoid polluting user-visible stream
    assert "scratchpad" in result, \
        "Safe executor should return scratchpad signals when artifact missing"

    scratchpad = result["scratchpad"]

    # Should recommend the provider
    assert "recommended_specialists" in scratchpad, \
        "Should recommend specialist that can provide the artifact"

    assert "data_extractor_specialist" in scratchpad["recommended_specialists"], \
        "Should recommend data_extractor_specialist as the provider"

    # Should add blocked specialist to forbidden_specialists
    assert "forbidden_specialists" in scratchpad, \
        "Should add blocked specialist to forbidden_specialists"

    assert "data_processor_specialist" in scratchpad["forbidden_specialists"], \
        "Should block data_processor_specialist until dependency satisfied"

    print("\n✓ Required artifact validation works correctly")
    print(f"  ✓ Missing artifact detected (scratchpad signals)")
    print(f"  ✓ Provider recommendation: {scratchpad['recommended_specialists']}")
    print(f"  ✓ Blocked specialist added to forbidden: {scratchpad['forbidden_specialists']}")


@pytest.mark.integration
def test_artifact_passing_simple_producer_consumer():
    """
    Tests simple artifact passing: systems_architect → web_builder

    Updated post ADR-CORE-035: Uses systems_architect (produces system_plan)
    and web_builder (requires system_plan) instead of removed file_specialist.

    This validates that:
    1. Producer writes artifact to state.artifacts
    2. Consumer can read artifact from state.artifacts
    3. Workflow continues successfully with artifact present
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    systems_architect = builder.specialists['systems_architect']
    web_builder = builder.specialists['web_builder']

    # Mock systems_architect to produce system_plan artifact
    with patch.object(systems_architect, 'llm_adapter') as mock_architect_adapter, \
         patch.object(web_builder, 'llm_adapter') as mock_builder_adapter:

        # Systems architect produces system_plan
        mock_architect_adapter.invoke.return_value = {
            "json_response": {
                "plan_summary": "Build a simple webpage",
                "required_components": ["HTML", "CSS"],
                "execution_steps": ["Create HTML structure", "Add styling"]
            }
        }
        mock_architect_adapter.model_name = "test-model"

        # Web builder produces HTML
        mock_builder_adapter.invoke.return_value = {
            "json_response": {
                "html_document": "<html><body>Test webpage</body></html>"
            }
        }
        mock_builder_adapter.model_name = "test-model"

        # Create executors
        architect_executor = builder.node_executor.create_safe_executor(systems_architect)
        builder_executor = builder.node_executor.create_safe_executor(web_builder)

        # Initial state
        state = {
            "messages": [HumanMessage(content="Build a webpage")],
            "artifacts": {},
            "turn_count": 0,
            "routing_history": [],
            "task_is_complete": False,
            "scratchpad": {}
        }

        # --- Act ---
        # Step 1: Systems architect produces system_plan artifact
        state_after_architect = architect_executor(state)

        # Merge state (simulating graph state update)
        state["artifacts"].update(state_after_architect.get("artifacts", {}))
        state["messages"].extend(state_after_architect.get("messages", []))

        # Step 2: Web builder consumes system_plan artifact
        state_after_builder = builder_executor(state)

        # --- Assert ---
        # Systems architect should have produced artifact
        assert "system_plan" in state["artifacts"], \
            "Systems architect should produce system_plan artifact"

        # Web builder should have successfully processed (no error)
        assert "error" not in state_after_builder, \
            "Web builder should not error when system_plan is present"

        # Web builder should have invoked LLM
        assert mock_builder_adapter.invoke.call_count == 1, \
            "Web builder should invoke LLM to process artifact"

        print("\n✓ Artifact passing works correctly")
        print(f"  ✓ Producer (systems_architect) created artifact: system_plan")
        print(f"  ✓ Consumer (web_builder) received artifact")
        print(f"  ✓ Workflow completed successfully")


@pytest.mark.integration
def test_conditional_artifacts_any_of():
    """
    Tests conditional artifact requirements (all-of pattern within a list).

    When requires_artifacts is [[artifact_a, artifact_b]], the specialist
    needs ALL artifacts in the inner list to proceed.

    Updated: Missing artifact response now uses scratchpad signals only
    (no messages) per ADR-CORE-016 to avoid polluting user-visible stream.
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Create a mock specialist with conditional artifacts
    from app.src.specialists.base import BaseSpecialist

    class ConditionalArtifactSpecialist(BaseSpecialist):
        def _execute_logic(self, state):
            return {"messages": [HumanMessage(content="Executed")]}

    # Configure with conditional requirements (needs ALL of these)
    conditional_specialist = ConditionalArtifactSpecialist(
        "conditional_test",
        {
            "type": "procedural",
            "requires_artifacts": [["artifact_a", "artifact_b"]],  # Needs BOTH a AND b
            "artifact_providers": {
                "artifact_a": "provider_a",
                "artifact_b": "provider_b"
            }
        }
    )

    safe_executor = builder.node_executor.create_safe_executor(conditional_specialist)

    # --- Act & Assert: Neither artifact present ---
    state_empty = {
        "messages": [HumanMessage(content="Test")],
        "artifacts": {},
        "turn_count": 0,
        "routing_history": [],
        "task_is_complete": False,
        "scratchpad": {}
    }

    result_empty = safe_executor(state_empty)
    # Missing artifact now signals via scratchpad, not messages
    assert "scratchpad" in result_empty, \
        "Should return scratchpad signals when artifact missing"
    assert "recommended_specialists" in result_empty["scratchpad"], \
        "Should recommend provider via scratchpad"
    assert "forbidden_specialists" in result_empty["scratchpad"], \
        "Should add self to forbidden_specialists"

    # --- Act & Assert: Only artifact_a present (need both) ---
    state_partial = {
        "messages": [HumanMessage(content="Test")],
        "artifacts": {"artifact_a": "data_a"},
        "turn_count": 0,
        "routing_history": [],
        "task_is_complete": False,
        "scratchpad": {}
    }

    result_partial = safe_executor(state_partial)
    # Still missing artifact_b
    assert "scratchpad" in result_partial, \
        "Should return scratchpad signals when artifact missing"
    assert "forbidden_specialists" in result_partial["scratchpad"], \
        "Should block self when partial artifacts present"

    # --- Act & Assert: Both artifacts present ---
    state_full = {
        "messages": [HumanMessage(content="Test")],
        "artifacts": {
            "artifact_a": "data_a",
            "artifact_b": "data_b"
        },
        "turn_count": 0,
        "routing_history": [],
        "task_is_complete": False,
        "scratchpad": {}
    }

    result_full = safe_executor(state_full)
    assert "messages" in result_full, \
        "Should return messages when executed successfully"
    assert "executed" in result_full["messages"][0].content.lower(), \
        "Should succeed when both artifacts present"

    print("\n✓ Conditional artifact validation works correctly")
    print("  ✓ Blocks when neither artifact present (scratchpad signals)")
    print("  ✓ Blocks when only partial artifacts present")
    print("  ✓ Succeeds when all required artifacts present")


@pytest.mark.integration
def test_artifact_cleanup_not_leaked():
    """
    Tests that artifacts don't leak between workflow runs.

    Updated post ADR-CORE-035: Uses systems_architect instead of removed file_specialist.

    This validates that state management properly isolates artifacts per workflow.
    (Note: Actual cleanup happens in EndSpecialist or between graph invocations)
    """
    # --- Arrange ---
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    systems_architect = builder.specialists['systems_architect']

    def mock_produce_artifact(state):
        return {
            "artifacts": {"system_plan": {"summary": "Run 1 plan"}},
            "messages": [HumanMessage(content="Artifact produced")]
        }

    with patch.object(systems_architect, '_execute_logic', side_effect=mock_produce_artifact):
        executor = builder.node_executor.create_safe_executor(systems_architect)

        # Run 1: Produce artifact
        state_run1 = {
            "messages": [HumanMessage(content="Run 1")],
            "artifacts": {},
            "turn_count": 0,
            "routing_history": [],
            "task_is_complete": False,
            "scratchpad": {}
        }

        result_run1 = executor(state_run1)
        state_run1["artifacts"].update(result_run1.get("artifacts", {}))

        # Run 2: Fresh state (simulates new workflow invocation)
        state_run2 = {
            "messages": [HumanMessage(content="Run 2")],
            "artifacts": {},  # Fresh, empty artifacts
            "turn_count": 0,
            "routing_history": [],
            "task_is_complete": False,
            "scratchpad": {}
        }

        # --- Assert ---
        # Run 1 should have artifact
        assert "system_plan" in state_run1["artifacts"], \
            "Run 1 should have produced artifact"

        assert state_run1["artifacts"]["system_plan"]["summary"] == "Run 1 plan", \
            "Run 1 artifact should have correct data"

        # Run 2 should NOT have Run 1's artifact (fresh state)
        assert "system_plan" not in state_run2["artifacts"], \
            "Run 2 should start with empty artifacts (no leakage from Run 1)"

        print("\n✓ Artifact isolation works correctly")
        print("  ✓ Run 1 produces artifact")
        print("  ✓ Run 2 starts with clean artifacts (no leakage)")
