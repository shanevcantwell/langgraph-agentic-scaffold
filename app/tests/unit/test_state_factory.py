# app/tests/unit/test_state_factory.py
"""Tests for state_factory.py — ADR-CORE-075 conversation context continuity."""
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from app.src.graph.state_factory import create_initial_state, create_test_state


class TestCreateInitialStateBaseline:
    """Baseline tests for create_initial_state (pre-existing behavior)."""

    def test_minimal_call(self):
        state = create_initial_state("Hello")
        assert len(state["messages"]) == 1
        assert isinstance(state["messages"][0], HumanMessage)
        assert state["messages"][0].content == "Hello"
        assert state["turn_count"] == 0
        assert state["task_is_complete"] is False

    def test_artifacts_include_user_request(self):
        state = create_initial_state("What is 2+2?")
        assert state["artifacts"]["user_request"] == "What is 2+2?"


class TestPriorMessages:
    """ADR-CORE-075: prior_messages merged into goal message for chat-template safety."""

    def test_prior_messages_merged_into_goal(self):
        """Prior context is merged into the single user message, not separate messages."""
        prior = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        # Single merged message
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)
        assert "First question" in msgs[0].content
        assert "First answer" in msgs[0].content
        assert "Follow-up" in msgs[0].content
        assert "[Context from prior runs]" in msgs[0].content
        assert "[Current request]" in msgs[0].content

    def test_hard_cap_last_six_messages(self):
        """Only last 6 prior messages are kept before merging."""
        prior = [
            {"role": "user", "content": f"Q{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"A{i}"}
            for i in range(10)
        ]
        state = create_initial_state("Latest", prior_messages=prior)
        msgs = state["messages"]
        assert len(msgs) == 1
        # First 4 messages (indices 0-3) should be dropped; index 4 onward kept
        assert "Q4" in msgs[0].content
        assert "Q0" not in msgs[0].content
        assert "Latest" in msgs[0].content

    def test_empty_content_skipped(self):
        prior = [
            {"role": "user", "content": "Real question"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "Another question"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        assert len(msgs) == 1
        assert "Real question" in msgs[0].content
        assert "Another question" in msgs[0].content
        assert "Follow-up" in msgs[0].content

    def test_unknown_role_included_if_has_content(self):
        """All roles with content are merged — role distinction no longer matters."""
        prior = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        assert len(msgs) == 1
        assert "You are helpful" in msgs[0].content
        assert "Hello" in msgs[0].content
        assert "Follow-up" in msgs[0].content

    def test_none_prior_messages_no_effect(self):
        state = create_initial_state("Hello", prior_messages=None)
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "Hello"

    def test_empty_list_prior_messages_no_effect(self):
        state = create_initial_state("Hello", prior_messages=[])
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "Hello"


class TestConversationId:
    """ADR-CORE-075: conversation_id tracking."""

    def test_conversation_id_stored_in_artifacts(self):
        state = create_initial_state("Hello", conversation_id="conv-123")
        assert state["artifacts"]["conversation_id"] == "conv-123"

    def test_no_conversation_id_not_in_artifacts(self):
        state = create_initial_state("Hello")
        assert "conversation_id" not in state["artifacts"]
