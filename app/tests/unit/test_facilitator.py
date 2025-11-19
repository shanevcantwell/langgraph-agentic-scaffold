import pytest
from unittest.mock import MagicMock
from app.src.specialists.facilitator_specialist import FacilitatorSpecialist
from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType

@pytest.fixture
def facilitator():
    config = {}
    specialist = FacilitatorSpecialist("facilitator_specialist", config)
    specialist.mcp_client = MagicMock()
    return specialist

def test_facilitator_executes_research_action(facilitator):
    # Arrange
    plan = ContextPlan(
        reasoning="Need info",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="LangGraph", description="Search")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }
    
    facilitator.mcp_client.call.return_value = [{"title": "Result", "url": "url", "snippet": "snippet"}]
    
    # Act
    result = facilitator.execute(state)
    
    # Assert
    assert "artifacts" in result
    assert "gathered_context" in result["artifacts"]
    assert "### Research: LangGraph" in result["artifacts"]["gathered_context"]
    
    facilitator.mcp_client.call.assert_called_with(
        service_name="researcher_specialist",
        function_name="search",
        parameters={"query": "LangGraph"}
    )

def test_facilitator_executes_read_file_action(facilitator):
    # Arrange
    plan = ContextPlan(
        reasoning="Need file",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="/path/to/file", description="Read")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }
    
    facilitator.mcp_client.call.return_value = "File content"
    
    # Act
    result = facilitator.execute(state)
    
    # Assert
    assert "### File: /path/to/file" in result["artifacts"]["gathered_context"]
    assert "File content" in result["artifacts"]["gathered_context"]

def test_facilitator_handles_missing_plan(facilitator):
    state = {"artifacts": {}}
    result = facilitator.execute(state)
    assert "error" in result

def test_facilitator_handles_mcp_error(facilitator):
    plan = ContextPlan(
        reasoning="Need info",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="LangGraph", description="Search")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }
    
    facilitator.mcp_client.call.side_effect = Exception("MCP Error")
    
    result = facilitator.execute(state)
    
    assert "### Error: LangGraph" in result["artifacts"]["gathered_context"]
