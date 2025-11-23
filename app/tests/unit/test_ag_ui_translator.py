import pytest
import asyncio
from app.src.interface.translator import AgUiTranslator
from app.src.interface.ag_ui_schema import EventType

async def mock_stream_generator():
    # 1. Run ID
    yield {"run_id": "test-run-123"}
    
    # 2. Node Output (Router)
    yield {
        "router_specialist": {
            "messages": ["some message"],
            "scratchpad": {"some": "data"}
        }
    }
    
    # 3. Node Output (End)
    yield {
        "end_specialist": {
            "task_is_complete": True,
            "artifacts": {"archive_report.md": "# Report"}
        }
    }

@pytest.mark.asyncio
async def test_translator_flow():
    translator = AgUiTranslator()
    events = []
    
    async for event in translator.translate(mock_stream_generator()):
        events.append(event)
        
    # Check Workflow Start
    assert events[0].type == EventType.WORKFLOW_START
    assert events[0].run_id == "test-run-123"

    # Check Router Node Start
    assert events[1].type == EventType.NODE_START
    assert events[1].source == "router_specialist"

    # Check Router Status
    assert events[2].type == EventType.STATUS_UPDATE
    assert events[2].source == "router_specialist"

    # Check Router Log
    assert events[3].type == EventType.LOG
    assert "Entering node: router_specialist" in events[3].data["message"]

    # Check Router Node End
    assert events[4].type == EventType.NODE_END
    assert events[4].source == "router_specialist"

    # Check End Node Start
    assert events[5].type == EventType.NODE_START
    assert events[5].source == "end_specialist"

    # Check End Status
    assert events[6].type == EventType.STATUS_UPDATE
    assert events[6].source == "end_specialist"
    
    # Check Workflow End
    last_event = events[-1]
    assert last_event.type == EventType.WORKFLOW_END
    assert last_event.data["final_state"]["task_is_complete"] is True
    assert last_event.data["archive"] == "# Report"

@pytest.mark.asyncio
async def test_translator_error_handling():
    async def error_generator():
        yield {"run_id": "error-run"}
        yield {
            "some_node": {
                "error": "Something went wrong",
                "scratchpad": {"error_report": "Detailed trace"}
            }
        }
        
    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(error_generator()):
        events.append(event)
        
    # Find error event
    error_events = [e for e in events if e.type == EventType.ERROR]
    assert len(error_events) == 1
    assert error_events[0].data["error"] == "Something went wrong"
    assert error_events[0].data["error_report"] == "Detailed trace"
