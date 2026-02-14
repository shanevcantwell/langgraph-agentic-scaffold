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
    """ADR-CORE-075: prior_messages threading."""

    def test_prior_messages_prepended_to_current(self):
        prior = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        assert len(msgs) == 3
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "First question"
        assert isinstance(msgs[1], AIMessage)
        assert msgs[1].content == "First answer"
        assert isinstance(msgs[2], HumanMessage)
        assert msgs[2].content == "Follow-up"

    def test_hard_cap_last_six_messages(self):
        """Only last 6 prior messages (3 user/assistant pairs) are kept."""
        prior = [
            {"role": "user", "content": f"Q{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"A{i}"}
            for i in range(10)
        ]
        state = create_initial_state("Latest", prior_messages=prior)
        msgs = state["messages"]
        # 6 capped + 1 current = 7
        assert len(msgs) == 7
        # First kept message should be from index 4 (10-6=4)
        assert msgs[0].content == "Q4"

    def test_empty_content_skipped(self):
        prior = [
            {"role": "user", "content": "Real question"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "Another question"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        # Empty assistant content skipped, so: Real question + Another question + Follow-up
        assert len(msgs) == 3
        assert msgs[0].content == "Real question"
        assert msgs[1].content == "Another question"
        assert msgs[2].content == "Follow-up"

    def test_unknown_role_skipped(self):
        prior = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        state = create_initial_state("Follow-up", prior_messages=prior)
        msgs = state["messages"]
        # system role skipped
        assert len(msgs) == 2
        assert msgs[0].content == "Hello"
        assert msgs[1].content == "Follow-up"

    def test_none_prior_messages_no_effect(self):
        state = create_initial_state("Hello", prior_messages=None)
        assert len(state["messages"]) == 1

    def test_empty_list_prior_messages_no_effect(self):
        state = create_initial_state("Hello", prior_messages=[])
        assert len(state["messages"]) == 1


class TestConversationId:
    """ADR-CORE-075: conversation_id tracking."""

    def test_conversation_id_stored_in_artifacts(self):
        state = create_initial_state("Hello", conversation_id="conv-123")
        assert state["artifacts"]["conversation_id"] == "conv-123"

    def test_no_conversation_id_not_in_artifacts(self):
        state = create_initial_state("Hello")
        assert "conversation_id" not in state["artifacts"]
