# app/tests/unit/test_thought_stream_events.py
"""
Unit tests for thought stream event emission.

These tests verify that AgUiTranslator and _stream_formatter correctly emit
events for ALL specialists, not just router_specialist. This addresses the
bug where image_specialist executed successfully but didn't appear in the
Glass Cockpit thought stream.

Test Strategy:
- Unit tests with mocked streams to verify event emission logic
- Covers image_specialist, triage_architect, default_responder, and other non-router nodes
- Tests both AgUiTranslator (for /v1/graph/stream/events) and _stream_formatter (for /v1/graph/stream)
"""
import pytest
import asyncio
import json
from typing import AsyncGenerator, Dict, Any, List

from app.src.interface.translator import AgUiTranslator
from app.src.interface.ag_ui_schema import EventType


# =============================================================================
# MOCK STREAM GENERATORS
# =============================================================================

async def mock_image_workflow_stream() -> AsyncGenerator[Dict[str, Any], None]:
    """
    Simulates LangGraph stream output for an image analysis workflow.

    Expected flow: triage_architect -> image_specialist -> default_responder_specialist
    (No router_specialist - direct routing from triage to image_specialist)
    """
    # 1. Run ID
    yield {"run_id": "test-image-run-001"}

    # 2. Triage Architect output
    yield {
        "triage_architect": {
            "scratchpad": {
                "query_type": "image_analysis",
                "context_plan": {"requires_image_specialist": True}
            },
            "next_specialist": "image_specialist"
        }
    }

    # 3. Image Specialist output (the one missing from thought stream)
    yield {
        "image_specialist": {
            "artifacts": {
                "image_description": "A colorful sunset over mountains with orange and purple hues."
            },
            "scratchpad": {
                "image_analysis_complete": True,
                "forbidden_specialists": ["image_specialist"]
            }
        }
    }

    # 4. Default Responder output
    yield {
        "default_responder_specialist": {
            "messages": [{"type": "ai", "content": "Based on the image analysis..."}],
            "scratchpad": {"response_generated": True}
        }
    }

    # 5. End Specialist output
    yield {
        "end_specialist": {
            "task_is_complete": True,
            "artifacts": {"archive_report.md": "# Analysis Report"}
        }
    }


async def mock_minimal_specialist_stream(specialist_name: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generates a minimal stream with a single specialist for targeted testing.
    """
    yield {"run_id": f"test-{specialist_name}-001"}
    yield {
        specialist_name: {
            "artifacts": {"test_artifact": "test_value"},
            "scratchpad": {"test_key": "test_value"}
        }
    }


async def mock_parallel_progenitors_stream() -> AsyncGenerator[Dict[str, Any], None]:
    """
    Simulates tiered chat with parallel progenitors.
    Tests that both parallel specialists emit events.
    """
    yield {"run_id": "test-tiered-chat-001"}

    # Triage
    yield {
        "triage_architect": {
            "scratchpad": {"query_type": "general_chat"},
            "next_specialist": "chat_specialist"
        }
    }

    # Parallel progenitors (in real execution, these come as separate chunks)
    yield {
        "progenitor_alpha_specialist": {
            "messages": [{"type": "ai", "content": "Alpha response..."}],
            "scratchpad": {"model": "gemini-2.0-flash"}
        }
    }

    yield {
        "progenitor_bravo_specialist": {
            "messages": [{"type": "ai", "content": "Bravo response..."}],
            "scratchpad": {"model": "gpt-4o-mini"}
        }
    }

    # Synthesizer
    yield {
        "tiered_synthesizer_specialist": {
            "messages": [{"type": "ai", "content": "Synthesized response..."}],
            "artifacts": {"final_user_response.md": "# Combined Response"}
        }
    }


# =============================================================================
# AgUiTranslator UNIT TESTS
# =============================================================================

class TestAgUiTranslatorImageWorkflow:
    """Tests that AgUiTranslator emits events for image_specialist."""

    @pytest.mark.asyncio
    async def test_image_specialist_emits_node_start(self):
        """Verify image_specialist triggers NODE_START event."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Find NODE_START events for image_specialist
        image_start_events = [
            e for e in events
            if e.type == EventType.NODE_START and e.source == "image_specialist"
        ]

        assert len(image_start_events) == 1, (
            f"Expected exactly 1 NODE_START for image_specialist, got {len(image_start_events)}. "
            f"All events: {[(e.type, e.source) for e in events]}"
        )

    @pytest.mark.asyncio
    async def test_image_specialist_emits_node_end(self):
        """Verify image_specialist triggers NODE_END event with artifacts."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Find NODE_END events for image_specialist
        image_end_events = [
            e for e in events
            if e.type == EventType.NODE_END and e.source == "image_specialist"
        ]

        assert len(image_end_events) == 1, (
            f"Expected exactly 1 NODE_END for image_specialist, got {len(image_end_events)}"
        )

        # Verify artifacts are included in NODE_END
        end_event = image_end_events[0]
        assert "artifacts" in end_event.data, "NODE_END should include artifacts"
        assert "image_description" in end_event.data["artifacts"], (
            "image_description artifact should be in NODE_END data"
        )

    @pytest.mark.asyncio
    async def test_image_specialist_emits_status_update(self):
        """Verify image_specialist triggers STATUS_UPDATE event."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Find STATUS_UPDATE events for image_specialist
        image_status_events = [
            e for e in events
            if e.type == EventType.STATUS_UPDATE and e.source == "image_specialist"
        ]

        assert len(image_status_events) >= 1, (
            f"Expected at least 1 STATUS_UPDATE for image_specialist, got {len(image_status_events)}"
        )

    @pytest.mark.asyncio
    async def test_all_specialists_emit_events_in_image_workflow(self):
        """Verify ALL specialists in the image workflow emit events."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Extract all unique sources that emitted NODE_START
        sources_with_node_start = {
            e.source for e in events if e.type == EventType.NODE_START
        }

        expected_specialists = {
            "triage_architect",
            "image_specialist",
            "default_responder_specialist",
            "end_specialist"
        }

        missing = expected_specialists - sources_with_node_start
        assert not missing, (
            f"Missing NODE_START events for specialists: {missing}. "
            f"Got NODE_START for: {sources_with_node_start}"
        )

    @pytest.mark.asyncio
    async def test_event_ordering_matches_execution_order(self):
        """Verify events are emitted in the correct execution order."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Extract NODE_START events in order
        node_start_order = [
            e.source for e in events if e.type == EventType.NODE_START
        ]

        expected_order = [
            "triage_architect",
            "image_specialist",
            "default_responder_specialist",
            "end_specialist"
        ]

        assert node_start_order == expected_order, (
            f"Event order mismatch. Expected: {expected_order}, Got: {node_start_order}"
        )


class TestAgUiTranslatorSpecialistCoverage:
    """Tests that AgUiTranslator handles various specialist types correctly."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("specialist_name", [
        "image_specialist",
        "file_operations_specialist",
        "data_extractor_specialist",
        "navigator_specialist",
        "web_builder",
        "chat_specialist",
    ])
    async def test_specialist_emits_all_event_types(self, specialist_name: str):
        """Verify each specialist type emits NODE_START, STATUS_UPDATE, LOG, NODE_END."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_minimal_specialist_stream(specialist_name)):
            events.append(event)

        # Get events for this specialist
        specialist_events = [e for e in events if e.source == specialist_name]
        event_types = {e.type for e in specialist_events}

        expected_types = {
            EventType.NODE_START,
            EventType.STATUS_UPDATE,
            EventType.LOG,
            EventType.NODE_END
        }

        missing = expected_types - event_types
        assert not missing, (
            f"{specialist_name} missing event types: {missing}. Got: {event_types}"
        )

    @pytest.mark.asyncio
    async def test_parallel_progenitors_both_emit_events(self):
        """Verify both parallel progenitors emit events independently."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_parallel_progenitors_stream()):
            events.append(event)

        # Check alpha progenitor
        alpha_events = [
            e for e in events
            if e.source == "progenitor_alpha_specialist" and e.type == EventType.NODE_START
        ]
        assert len(alpha_events) == 1, "progenitor_alpha_specialist should emit NODE_START"

        # Check bravo progenitor
        bravo_events = [
            e for e in events
            if e.source == "progenitor_bravo_specialist" and e.type == EventType.NODE_START
        ]
        assert len(bravo_events) == 1, "progenitor_bravo_specialist should emit NODE_START"


class TestAgUiTranslatorDataIntegrity:
    """Tests that event data contains expected information."""

    @pytest.mark.asyncio
    async def test_node_end_contains_scratchpad(self):
        """Verify NODE_END events include scratchpad data."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Find image_specialist NODE_END
        image_end = next(
            (e for e in events
             if e.type == EventType.NODE_END and e.source == "image_specialist"),
            None
        )

        assert image_end is not None, "image_specialist NODE_END not found"
        assert "scratchpad" in image_end.data, "NODE_END should include scratchpad"
        assert image_end.data["scratchpad"].get("image_analysis_complete") is True

    @pytest.mark.asyncio
    async def test_workflow_end_contains_accumulated_state(self):
        """Verify WORKFLOW_END includes accumulated state from all specialists."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Find WORKFLOW_END
        workflow_end = next(
            (e for e in events if e.type == EventType.WORKFLOW_END),
            None
        )

        assert workflow_end is not None, "WORKFLOW_END event not found"
        assert "final_state" in workflow_end.data, "WORKFLOW_END should have final_state"

        # Verify artifacts from image_specialist are accumulated
        final_state = workflow_end.data["final_state"]
        artifacts = final_state.get("artifacts", [])
        assert "image_description" in artifacts or "archive_report.md" in artifacts, (
            f"Expected artifacts to include image_description. Got: {artifacts}"
        )


# =============================================================================
# _stream_formatter UNIT TESTS
# =============================================================================
# Note: These test the /v1/graph/stream endpoint's formatter which is used by
# the Glass Cockpit UI. We need to verify it emits the right status messages.

class TestStreamFormatterImageWorkflow:
    """Tests that _stream_formatter emits status updates for image_specialist."""

    @pytest.mark.asyncio
    async def test_image_specialist_status_emitted(self):
        """Verify _stream_formatter emits status for image_specialist."""
        from app.src.api import _stream_formatter

        chunks = []
        async for chunk in _stream_formatter(mock_image_workflow_stream()):
            chunks.append(chunk)

        # Parse the SSE data lines
        status_updates = []
        for chunk in chunks:
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if "status" in data:
                        status_updates.append(data["status"])
                except json.JSONDecodeError:
                    pass

        # Check for image_specialist status update
        image_statuses = [s for s in status_updates if "image_specialist" in s]
        assert len(image_statuses) >= 1, (
            f"Expected status update for image_specialist. "
            f"Got statuses: {status_updates}"
        )

    @pytest.mark.asyncio
    async def test_all_specialists_have_status_updates(self):
        """Verify all specialists in image workflow emit status updates."""
        from app.src.api import _stream_formatter

        chunks = []
        async for chunk in _stream_formatter(mock_image_workflow_stream()):
            chunks.append(chunk)

        # Parse and collect specialist names from status updates
        specialist_names = set()
        for chunk in chunks:
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if "status" in data:
                        # Extract specialist name from "Executing specialist: <name>..."
                        import re
                        match = re.search(r'Executing specialist: (\w+)', data["status"])
                        if match:
                            specialist_names.add(match.group(1))
                except json.JSONDecodeError:
                    pass

        expected = {"triage_architect", "image_specialist", "default_responder_specialist", "end_specialist"}
        missing = expected - specialist_names

        assert not missing, (
            f"Missing status updates for specialists: {missing}. "
            f"Got updates for: {specialist_names}"
        )

    @pytest.mark.asyncio
    async def test_logs_emitted_for_ui_timing(self):
        """Verify 'Entering node:' logs are emitted for UI timing tracking."""
        from app.src.api import _stream_formatter

        chunks = []
        async for chunk in _stream_formatter(mock_image_workflow_stream()):
            chunks.append(chunk)

        # Parse and collect logs
        logs = []
        for chunk in chunks:
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if "logs" in data:
                        logs.append(data["logs"])
                except json.JSONDecodeError:
                    pass

        # Check for image_specialist log
        image_logs = [l for l in logs if "image_specialist" in l]
        assert len(image_logs) >= 1, (
            f"Expected 'Entering node: image_specialist' log. Got logs: {logs}"
        )


class TestStreamFormatterEventCompleteness:
    """Tests that _stream_formatter emits complete event information."""

    @pytest.mark.asyncio
    async def test_scratchpad_reasoning_streamed(self):
        """Verify reasoning fields from scratchpad are streamed."""
        async def mock_with_reasoning():
            yield {"run_id": "test-reasoning-001"}
            yield {
                "triage_architect": {
                    "scratchpad": {
                        "routing_reasoning": "Image detected, routing to image_specialist",
                        "context_plan": {"key": "value"}
                    }
                }
            }

        from app.src.api import _stream_formatter

        chunks = []
        async for chunk in _stream_formatter(mock_with_reasoning()):
            chunks.append(chunk)

        # Look for scratchpad data in streamed chunks
        scratchpad_found = False
        for chunk in chunks:
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if "scratchpad" in data:
                        scratchpad_found = True
                        # Verify reasoning field is present
                        if "routing_reasoning" in data["scratchpad"]:
                            break
                except json.JSONDecodeError:
                    pass

        assert scratchpad_found, "Scratchpad reasoning should be streamed for thought stream"

    @pytest.mark.asyncio
    async def test_final_state_includes_image_artifacts(self):
        """Verify final_state includes artifacts from image_specialist."""
        from app.src.api import _stream_formatter

        chunks = []
        async for chunk in _stream_formatter(mock_image_workflow_stream()):
            chunks.append(chunk)

        # Find final_state in chunks
        final_state = None
        for chunk in chunks:
            if chunk.startswith("data: "):
                try:
                    data = json.loads(chunk[6:].strip())
                    if "final_state" in data:
                        final_state = data["final_state"]
                except json.JSONDecodeError:
                    pass

        assert final_state is not None, "final_state should be in streamed output"
        artifacts = final_state.get("artifacts", [])
        assert "image_description" in artifacts, (
            f"image_description should be in final_state artifacts. Got: {artifacts}"
        )


# =============================================================================
# EVENT FLOW DIAGNOSTIC TESTS
# =============================================================================

class TestEventFlowDiagnostics:
    """
    Tests to help diagnose where events might be lost in the flow.
    These tests emit detailed diagnostic information when they fail.
    """

    @pytest.mark.asyncio
    async def test_translator_receives_all_chunks(self):
        """Verify translator receives all chunks from the stream."""
        chunks_received = []

        async def instrumented_stream():
            async for chunk in mock_image_workflow_stream():
                chunks_received.append(chunk)
                yield chunk

        translator = AgUiTranslator()
        events = []
        async for event in translator.translate(instrumented_stream()):
            events.append(event)

        # We expect: run_id + 4 specialists = 5 chunks
        assert len(chunks_received) == 5, (
            f"Expected 5 chunks, got {len(chunks_received)}: {chunks_received}"
        )

        # Map chunks to expected specialists
        specialist_chunks = [c for c in chunks_received if "run_id" not in c]
        specialist_names = [list(c.keys())[0] for c in specialist_chunks]

        expected = ["triage_architect", "image_specialist", "default_responder_specialist", "end_specialist"]
        assert specialist_names == expected, (
            f"Chunk order mismatch. Expected: {expected}, Got: {specialist_names}"
        )

    @pytest.mark.asyncio
    async def test_event_count_matches_expected(self):
        """Verify the total number of events emitted matches expected."""
        translator = AgUiTranslator()
        events = []

        async for event in translator.translate(mock_image_workflow_stream()):
            events.append(event)

        # Count events by type
        event_counts = {}
        for e in events:
            event_counts[e.type] = event_counts.get(e.type, 0) + 1

        # Expected:
        # - 1 WORKFLOW_START
        # - 4 NODE_START (triage, image, default_responder, end)
        # - 4 STATUS_UPDATE
        # - 4 LOG
        # - 4 NODE_END
        # - 1 WORKFLOW_END

        assert event_counts.get(EventType.WORKFLOW_START, 0) == 1, "Expected 1 WORKFLOW_START"
        assert event_counts.get(EventType.NODE_START, 0) == 4, f"Expected 4 NODE_START, got {event_counts.get(EventType.NODE_START, 0)}"
        assert event_counts.get(EventType.NODE_END, 0) == 4, f"Expected 4 NODE_END, got {event_counts.get(EventType.NODE_END, 0)}"
        assert event_counts.get(EventType.WORKFLOW_END, 0) == 1, "Expected 1 WORKFLOW_END"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
