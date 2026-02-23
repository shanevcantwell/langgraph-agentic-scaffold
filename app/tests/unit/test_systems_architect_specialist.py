import pytest
from unittest.mock import MagicMock, ANY
from pydantic import ValidationError
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
        "execution_steps": ["Generate HTML", "Generate CSS"],
        "acceptance_criteria": "An index.html file exists with valid HTML structure and a linked styles.css file.",
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
    # Issue #171: SA entry point writes task_plan (not system_plan)
    assert "task_plan" in result_state["artifacts"]
    assert result_state["artifacts"]["task_plan"]["plan_summary"] == mock_plan_summary
    assert "Generate HTML" in result_state["artifacts"]["task_plan"]["execution_steps"]

def test_systems_architect_handles_no_json_response(systems_architect_specialist):
    """Tests that the specialist raises an error if LLM returns no JSON response."""
    # Arrange
    systems_architect_specialist.llm_adapter.invoke.return_value = {"json_response": None}

    initial_state = {"messages": [HumanMessage(content="Plan something.")]}

    # Act & Assert
    with pytest.raises(ValueError):
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
            "execution_steps": ["Create directories", "Move files"],
            "acceptance_criteria": "The target directory contains subdirectories for each category with files sorted accordingly.",
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
            "execution_steps": [],
            "acceptance_criteria": "The workspace contains organized files matching the user request criteria.",
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

        with pytest.raises(ValueError):
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


# =============================================================================
# Issue #216: acceptance_criteria Validator
# =============================================================================

# --- Shared valid fields for reuse in validator tests ---
_VALID_PLAN_FIELDS = {
    "plan_summary": "Test plan.",
    "required_components": [],
    "execution_steps": ["Do the thing."],
}


class TestAcceptanceCriteriaValidator:
    """Tests for SystemPlan.acceptance_criteria field_validator (#216).

    The validator enforces:
    1. acceptance_criteria is required (not optional)
    2. Minimum 30 characters after stripping whitespace
    3. Rejects placeholder-only content (periods, spaces, ellipses)
    """

    def test_valid_acceptance_criteria(self):
        """A substantive description passes validation."""
        plan = SystemPlan(
            **_VALID_PLAN_FIELDS,
            acceptance_criteria="The output directory contains three subdirectories with at least two files each.",
        )
        assert len(plan.acceptance_criteria) > 30

    def test_valid_at_exactly_30_chars(self):
        """Boundary: exactly 30 characters should pass."""
        criteria = "A" * 30  # 30 chars of real content
        plan = SystemPlan(**_VALID_PLAN_FIELDS, acceptance_criteria=criteria)
        assert plan.acceptance_criteria == criteria

    def test_missing_acceptance_criteria_raises(self):
        """Omitting acceptance_criteria entirely is a required-field error."""
        with pytest.raises(ValidationError, match="acceptance_criteria"):
            SystemPlan(**_VALID_PLAN_FIELDS)

    @pytest.mark.parametrize("short_value", [
        "",
        " ",
        "Done.",
        "Files exist.",
        "A" * 29,  # one char below threshold
        "..",       # placeholder, but caught by length first
        "...",
        "…",       # unicode ellipsis, also too short
        "  ...  ", # stripped to "...", length 3
    ])
    def test_too_short_raises(self, short_value):
        """Values under 30 chars (after strip) are rejected.

        Note: short placeholder strings (e.g. '...') are caught by the length
        check first, not the placeholder check. This is correct — both checks
        reject the value, length just fires first.
        """
        with pytest.raises(ValidationError, match="too short"):
            SystemPlan(**_VALID_PLAN_FIELDS, acceptance_criteria=short_value)

    @pytest.mark.parametrize("placeholder_value", [
        "." * 30,           # 30 periods — passes length, caught by placeholder
        "." * 50,           # 50 periods
        ". " * 20,          # periods with spaces, 39 chars stripped
        "…" * 30,           # 30 unicode ellipses
        "  " + "." * 35 + "  ",  # padded periods, 35 after strip
    ])
    def test_placeholder_only_raises(self, placeholder_value):
        """Strings >= 30 chars made entirely of periods, spaces, and ellipsis characters
        are rejected by the placeholder check (they pass the length check).
        """
        with pytest.raises(ValidationError, match="placeholder"):
            SystemPlan(**_VALID_PLAN_FIELDS, acceptance_criteria=placeholder_value)

    def test_real_content_with_ellipsis_passes(self):
        """Content that happens to contain ellipsis but has real text passes.

        This guards against false positives from user prompts with quoted ellipses.
        """
        criteria = "The workspace contains all original files… organized into category subdirectories."
        plan = SystemPlan(**_VALID_PLAN_FIELDS, acceptance_criteria=criteria)
        assert "…" in plan.acceptance_criteria

    def test_whitespace_only_raises(self):
        """All-whitespace strings are rejected (too short after strip)."""
        with pytest.raises(ValidationError, match="too short"):
            SystemPlan(**_VALID_PLAN_FIELDS, acceptance_criteria="     \t\n    ")


class TestAcceptanceCriteriaErrorPath:
    """Tests that ValidationError from the acceptance_criteria validator
    propagates correctly through SA's _generate_plan() → _execute_logic().

    SafeExecutor catches these exceptions in production. Here we verify the
    exception surfaces from the specialist code itself (SafeExecutor is tested
    separately).
    """

    def test_empty_acceptance_criteria_raises_through_execute_logic(self, systems_architect_specialist):
        """When LLM returns empty acceptance_criteria, _execute_logic raises ValidationError."""
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": {
                "plan_summary": "Categorize text files by topic.",
                "required_components": ["project_director"],
                "execution_steps": ["Read files", "Create directories", "Move files"],
                "acceptance_criteria": "",
            }
        }
        initial_state = {"messages": [HumanMessage(content="Categorize files.")]}

        with pytest.raises(ValidationError, match="too short"):
            systems_architect_specialist._execute_logic(initial_state)

    def test_placeholder_acceptance_criteria_raises_through_execute_logic(self, systems_architect_specialist):
        """When LLM returns long placeholder acceptance_criteria, _execute_logic raises ValidationError."""
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": {
                "plan_summary": "Organize workspace.",
                "required_components": [],
                "execution_steps": ["Read directory"],
                "acceptance_criteria": "." * 40,  # 40 periods — passes length, caught by placeholder
            }
        }
        initial_state = {"messages": [HumanMessage(content="Organize workspace.")]}

        with pytest.raises(ValidationError, match="placeholder"):
            systems_architect_specialist._execute_logic(initial_state)

    def test_missing_acceptance_criteria_raises_through_execute_logic(self, systems_architect_specialist):
        """When LLM omits acceptance_criteria entirely, _execute_logic raises ValidationError."""
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": {
                "plan_summary": "Some plan.",
                "required_components": [],
                "execution_steps": ["Step one"],
                # acceptance_criteria omitted entirely
            }
        }
        initial_state = {"messages": [HumanMessage(content="Do something.")]}

        with pytest.raises(ValidationError, match="acceptance_criteria"):
            systems_architect_specialist._execute_logic(initial_state)

    def test_mcp_create_plan_also_validates(self, systems_architect_specialist):
        """The MCP tool path (_generate_plan via create_plan) enforces the same validator."""
        systems_architect_specialist.llm_adapter.invoke.return_value = {
            "json_response": {
                "plan_summary": "A plan via MCP.",
                "required_components": [],
                "execution_steps": [],
                "acceptance_criteria": "",
            }
        }

        with pytest.raises(ValidationError, match="too short"):
            systems_architect_specialist.create_plan(
                context="Plan via MCP",
                artifact_key="test_plan",
            )