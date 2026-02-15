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
    # ADR-CORE-075: conversation_id defaults to None when not in stream
    assert last_event.data["conversation_id"] is None

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


@pytest.mark.asyncio
async def test_translator_handles_interrupt_event():
    """
    Regression test for Bug #50: AgUiTranslator must handle __interrupt__ events.

    When DialogueSpecialist calls interrupt(), LangGraph yields a chunk with
    __interrupt__ key. The translator must emit CLARIFICATION_REQUIRED event
    with thread_id for resume capability.
    """
    async def interrupt_generator():
        yield {"run_id": "interrupt-run-456"}
        yield {
            "facilitator_specialist": {
                "messages": ["starting facilitator"],
                "scratchpad": {}
            }
        }
        # Simulate LangGraph interrupt event (as returned by astream)
        yield {
            "__interrupt__": [
                {
                    "value": {
                        "questions": [
                            {"question": "Which file?", "reason": "Ambiguous reference"}
                        ]
                    },
                    "resumable": True
                }
            ]
        }
        # Nothing after interrupt - workflow is paused

    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(interrupt_generator()):
        events.append(event)

    # Should have: WORKFLOW_START, NODE_START, STATUS_UPDATE, LOG, NODE_END, CLARIFICATION_REQUIRED
    # NO WORKFLOW_END - workflow is paused, not complete

    # Find clarification event
    clarification_events = [e for e in events if e.type == EventType.CLARIFICATION_REQUIRED]
    assert len(clarification_events) == 1, f"Expected 1 clarification event, got {len(clarification_events)}"

    clarification = clarification_events[0]
    assert clarification.source == "system"
    assert clarification.data["resumable"] is True
    assert clarification.data["thread_id"] == "interrupt-run-456"
    assert len(clarification.data["questions"]) == 1
    assert clarification.data["questions"][0]["question"] == "Which file?"

    # Verify NO workflow_end event (workflow is paused)
    end_events = [e for e in events if e.type == EventType.WORKFLOW_END]
    assert len(end_events) == 0, "Should not emit WORKFLOW_END when interrupted"


@pytest.mark.asyncio
async def test_translator_handles_interrupt_with_object_payload():
    """
    Test interrupt handling when payload has .value attribute (namedtuple form).
    """
    class InterruptPayload:
        """Simulates LangGraph's Interrupt namedtuple."""
        def __init__(self, value, resumable=True):
            self.value = value
            self.resumable = resumable

    async def interrupt_with_object():
        yield {"run_id": "object-run"}
        yield {
            "__interrupt__": [
                InterruptPayload(
                    value={"questions": [{"question": "What format?", "reason": "Need clarification"}]},
                    resumable=True
                )
            ]
        }

    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(interrupt_with_object()):
        events.append(event)

    clarification_events = [e for e in events if e.type == EventType.CLARIFICATION_REQUIRED]
    assert len(clarification_events) == 1
    assert clarification_events[0].data["questions"][0]["question"] == "What format?"


@pytest.mark.asyncio
async def test_translator_forwards_facilitator_ask_user_payload():
    """
    ADR-CORE-042: Facilitator ASK_USER sends {question, reason, action_type}
    (singular), not {questions: [...]}.  The translator must forward the full
    payload so the UI can render the question text.
    """
    async def facilitator_interrupt():
        yield {"run_id": "ask-user-run"}
        yield {
            "__interrupt__": [
                {
                    "value": {
                        "question": "What tone should the backronym have?",
                        "reason": "Clarify desired tone",
                        "action_type": "ask_user"
                    },
                    "resumable": True
                }
            ]
        }

    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(facilitator_interrupt()):
        events.append(event)

    clarification_events = [e for e in events if e.type == EventType.CLARIFICATION_REQUIRED]
    assert len(clarification_events) == 1

    data = clarification_events[0].data
    # Full payload forwarded — question (singular) is present
    assert data["question"] == "What tone should the backronym have?"
    assert data["reason"] == "Clarify desired tone"
    assert data["action_type"] == "ask_user"
    # thread_id and resumable injected by translator
    assert data["thread_id"] == "ask-user-run"
    assert data["resumable"] is True


@pytest.mark.asyncio
async def test_translator_forwards_conversation_id_in_workflow_end():
    """
    ADR-CORE-075: conversation_id from runner must appear in the workflow_end
    event data so the UI can store it for multi-turn threading (#181).
    """
    async def stream_with_conversation_id():
        yield {"run_id": "conv-run"}
        yield {"conversation_id": "conv-abc-123"}
        yield {
            "router_specialist": {
                "messages": ["routed"],
                "scratchpad": {}
            }
        }

    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(stream_with_conversation_id()):
        events.append(event)

    # conversation_id should NOT appear as a node
    node_sources = [e.source for e in events if e.type == EventType.NODE_START]
    assert "conversation_id" not in node_sources

    # conversation_id should appear in workflow_end data
    end_event = [e for e in events if e.type == EventType.WORKFLOW_END][0]
    assert end_event.data["conversation_id"] == "conv-abc-123"


@pytest.mark.asyncio
async def test_translator_skips_thread_id_metadata():
    """
    Regression test for Bug #52: thread_id chunk must not be processed as node.

    When runner yields {"thread_id": "xxx"}, the translator should skip it
    (like run_id), not emit NODE_START/NODE_END events for "thread_id".
    """
    async def stream_with_thread_id():
        yield {"run_id": "test-run"}
        yield {"thread_id": "test-run"}  # Metadata, not a node
        yield {
            "router_specialist": {
                "messages": ["routed"],
                "scratchpad": {}
            }
        }

    translator = AgUiTranslator()
    events = []
    async for event in translator.translate(stream_with_thread_id()):
        events.append(event)

    # Find all node sources
    node_sources = [e.source for e in events if e.type == EventType.NODE_START]

    # thread_id should NOT appear as a node
    assert "thread_id" not in node_sources, "thread_id metadata incorrectly processed as node"

    # router_specialist should be the only node
    assert "router_specialist" in node_sources
