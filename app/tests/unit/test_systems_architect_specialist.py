import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.systems_architect import SystemsArchitect
from app.src.specialists.schemas import SystemPlan
from app.src.llm.adapter import StandardizedLLMRequest

@pytest.fixture
def systems_architect_specialist(initialized_specialist_factory):
    """Fixture for an initialized SystemsArchitect."""
    return initialized_specialist_factory("SystemsArchitect")

def test_systems_architect_creates_system_plan(systems_architect_specialist):
    """Tests that the specialist successfully creates a system plan."""
    # Arrange
    mock_plan_summary = "Design a simple web page."
    mock_json_response = {
        "plan_summary": mock_plan_summary,
        "required_components": ["web_builder"],
        "execution_steps": ["Generate HTML", "Generate CSS"]
    }
    systems_architect_specialist.llm_adapter.invoke.return_value = {
        "json_response": mock_json_response
    }

    initial_state = {"messages": [HumanMessage(content="I need a plan for a web page.")]}

    # Act
    result_state = systems_architect_specialist._execute_logic(initial_state)

    # Assert
    systems_architect_specialist.llm_adapter.invoke.assert_called_once()
    called_request = systems_architect_specialist.llm_adapter.invoke.call_args[0][0]
    assert isinstance(called_request, StandardizedLLMRequest)
    assert called_request.output_model_class == SystemPlan

    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert mock_plan_summary in result_state["messages"][0].content

    assert "artifacts" in result_state
    assert "system_plan" in result_state["artifacts"]
    assert result_state["artifacts"]["system_plan"]["plan_summary"] == mock_plan_summary # This is a dict now
    assert "Generate HTML" in result_state["artifacts"]["system_plan"]["execution_steps"]

    # "Not me" pattern: specialist adds itself to forbidden list after completing its job
    assert "forbidden_specialists" in result_state["scratchpad"]
    assert "systems_architect" in result_state["scratchpad"]["forbidden_specialists"]

def test_systems_architect_handles_no_json_response(systems_architect_specialist):
    """Tests that the specialist raises an error if LLM returns no JSON response."""
    # Arrange
    systems_architect_specialist.llm_adapter.invoke.return_value = {"json_response": None}

    initial_state = {"messages": [HumanMessage(content="Plan something.")]}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid plan from the LLM."):
        systems_architect_specialist._execute_logic(initial_state)

def test_systems_architect_handles_malformed_json_response(systems_architect_specialist):
    """Tests that the specialist raises an error if LLM returns malformed JSON."""
    # Arrange
    # Missing required fields 'required_components' and 'execution_steps' in SystemPlan
    systems_architect_specialist.llm_adapter.invoke.return_value = {
        "json_response": {"plan_summary": "Invalid plan."}
    }

    initial_state = {"messages": [HumanMessage(content="Plan something.")]}

    # Act & Assert
    with pytest.raises(Exception): # Expecting Pydantic validation error
        systems_architect_specialist._execute_logic(initial_state)


# =============================================================================
# Issue #115: SA as MCP Tool
# =============================================================================

class TestSystemsArchitectMCPTool:
    """Tests for Systems Architect's MCP tool interface (Issue #115)."""

    def test_create_plan_returns_artifact_with_specified_key(self, systems_architect_specialist):
        """
        create_plan() should return artifacts with the caller-specified key.
        This allows callers (e.g., Exit Interview) to control where the plan is stored.
        """
        mock_json_response = {
            "plan_summary": "Sort files into categories",
            "required_components": ["project_director"],
            "execution_steps": ["Create directories", "Move files"]
        }
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": mock_json_response
        }

        result = systems_architect_specialist.create_plan(
            context="Sort files into a-m and n-z directories",
            artifact_key="exit_plan"
        )

        # Should return artifact with the specified key
        assert "artifacts" in result
        assert "exit_plan" in result["artifacts"]
        assert result["artifacts"]["exit_plan"]["plan_summary"] == "Sort files into categories"

    def test_create_plan_uses_context_as_human_message(self, systems_architect_specialist):
        """
        create_plan() should pass context as a HumanMessage to the LLM.
        """
        mock_json_response = {
            "plan_summary": "Test plan",
            "required_components": [],
            "execution_steps": []
        }
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": mock_json_response
        }

        systems_architect_specialist.create_plan(
            context="User wants to organize files",
            artifact_key="my_plan"
        )

        # Verify LLM was called with HumanMessage containing context
        call_args = systems_architect_specialist.llm_adapter.invoke.call_args[0][0]
        assert len(call_args.messages) == 1
        assert isinstance(call_args.messages[0], HumanMessage)
        assert call_args.messages[0].content == "User wants to organize files"

    def test_create_plan_raises_on_no_json_response(self, systems_architect_specialist):
        """
        create_plan() should raise ValueError if LLM returns no JSON response.
        """
        systems_architect_specialist.llm_adapter.invoke.return_value = {"json_response": None}

        with pytest.raises(ValueError, match="failed to get a valid plan from the LLM"):
            systems_architect_specialist.create_plan(context="Plan something", artifact_key="plan")

    def test_register_mcp_services_exposes_create_plan(self, systems_architect_specialist):
        """
        register_mcp_services() should register create_plan with the MCP registry.
        """
        mock_registry = MagicMock()

        systems_architect_specialist.register_mcp_services(mock_registry)

        mock_registry.register_service.assert_called_once()
        call_args = mock_registry.register_service.call_args
        assert call_args[0][0] == "systems_architect"  # service name
        assert "create_plan" in call_args[0][1]  # methods dict
        assert call_args[0][1]["create_plan"] == systems_architect_specialist.create_plan