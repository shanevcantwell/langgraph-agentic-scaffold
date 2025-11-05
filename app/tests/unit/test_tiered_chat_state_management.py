# app/tests/unit/test_tiered_chat_state_management.py
"""
Unit tests for CORE-CHAT-002 State Management Pattern.

These tests verify the critical state management pattern for parallel execution:
- Progenitor specialists (parallel nodes) write ONLY to 'artifacts'
- TieredSynthesizer (join node) writes to 'messages'
- This prevents message pollution and enables proper multi-turn cross-referencing

Part of BUGFIX: CORE-CHAT-002 State Management
"""
import pytest
from unittest.mock import ANY
from langchain_core.messages import AIMessage, HumanMessage


class TestProgenitorStateManagement:
    """Tests that progenitors follow the state management pattern for parallel execution."""

    def test_progenitor_alpha_does_not_modify_messages(self, initialized_specialist_factory):
        """Verifies ProgenitorAlpha does NOT append to messages (critical for parallel pattern)."""
        # Arrange
        progenitor_alpha = initialized_specialist_factory("ProgenitorAlphaSpecialist")
        progenitor_alpha.llm_adapter.invoke.return_value = {
            "text_response": "Alpha perspective response"
        }

        initial_state = {
            "messages": [HumanMessage(content="Test question")]
        }

        # Act
        result_state = progenitor_alpha._execute_logic(initial_state)

        # Assert - CRITICAL: No messages key in return value
        assert "messages" not in result_state, (
            "ProgenitorAlpha MUST NOT return 'messages' key. "
            "Parallel nodes write to artifacts, join nodes write to messages."
        )

        # Verify response IS in artifacts
        assert "artifacts" in result_state
        assert "alpha_response" in result_state["artifacts"]
        assert isinstance(result_state["artifacts"]["alpha_response"], str)

    def test_progenitor_bravo_does_not_modify_messages(self, initialized_specialist_factory):
        """Verifies ProgenitorBravo does NOT append to messages (critical for parallel pattern)."""
        # Arrange
        progenitor_bravo = initialized_specialist_factory("ProgenitorBravoSpecialist")
        progenitor_bravo.llm_adapter.invoke.return_value = {
            "text_response": "Bravo perspective response"
        }

        initial_state = {
            "messages": [HumanMessage(content="Test question")]
        }

        # Act
        result_state = progenitor_bravo._execute_logic(initial_state)

        # Assert - CRITICAL: No messages key in return value
        assert "messages" not in result_state, (
            "ProgenitorBravo MUST NOT return 'messages' key. "
            "Parallel nodes write to artifacts, join nodes write to messages."
        )

        # Verify response IS in artifacts
        assert "artifacts" in result_state
        assert "bravo_response" in result_state["artifacts"]
        assert isinstance(result_state["artifacts"]["bravo_response"], str)

    def test_progenitors_write_only_to_artifacts(self, initialized_specialist_factory):
        """Verifies both progenitors write responses to artifacts, not messages."""
        # Arrange
        alpha = initialized_specialist_factory("ProgenitorAlphaSpecialist")
        bravo = initialized_specialist_factory("ProgenitorBravoSpecialist")

        alpha.llm_adapter.invoke.return_value = {"text_response": "Alpha response"}
        bravo.llm_adapter.invoke.return_value = {"text_response": "Bravo response"}

        state = {"messages": [HumanMessage(content="Test")]}

        # Act
        alpha_result = alpha._execute_logic(state)
        bravo_result = bravo._execute_logic(state)

        # Assert - Both write to artifacts only
        assert "messages" not in alpha_result
        assert "messages" not in bravo_result
        assert "alpha_response" in alpha_result["artifacts"]
        assert "bravo_response" in bravo_result["artifacts"]


class TestSynthesizerStateManagement:
    """Tests that TieredSynthesizer correctly appends to messages (join node behavior)."""

    def test_synthesizer_does_append_to_messages(self, initialized_specialist_factory):
        """Verifies TieredSynthesizer DOES append to messages (join node pattern)."""
        # Arrange
        synthesizer = initialized_specialist_factory("TieredSynthesizerSpecialist")

        state = {
            "messages": [HumanMessage(content="Test question")],
            "artifacts": {
                "alpha_response": "Alpha perspective",
                "bravo_response": "Bravo perspective"
            }
        }

        # Act
        result_state = synthesizer._execute_logic(state)

        # Assert - CRITICAL: Synthesizer MUST return messages key
        assert "messages" in result_state, (
            "TieredSynthesizer MUST return 'messages' key. "
            "Join nodes write to messages after combining parallel results."
        )

        # Should be exactly one message (the synthesis status)
        assert len(result_state["messages"]) == 1
        assert isinstance(result_state["messages"][0], AIMessage)

    def test_synthesizer_sets_task_complete(self, initialized_specialist_factory):
        """Verifies TieredSynthesizer signals workflow completion."""
        # Arrange
        synthesizer = initialized_specialist_factory("TieredSynthesizerSpecialist")

        state = {
            "messages": [HumanMessage(content="Test")],
            "artifacts": {
                "alpha_response": "Alpha",
                "bravo_response": "Bravo"
            }
        }

        # Act
        result_state = synthesizer._execute_logic(state)

        # Assert - Synthesizer completes the task
        assert result_state.get("task_is_complete") is True


class TestMultiTurnStateManagement:
    """Tests that state management pattern enables proper multi-turn conversations."""

    def test_multi_turn_history_accumulation(self, initialized_specialist_factory):
        """
        Verifies that multi-turn conversations accumulate clean message history.

        With correct state management:
        - Turn 1: User -> [Alpha, Bravo] -> Synthesizer -> 2 messages total
        - Turn 2: User -> [Alpha, Bravo] -> Synthesizer -> 4 messages total

        Bug behavior would result in 6 messages (progenitors polluting history).
        """
        # Arrange
        alpha = initialized_specialist_factory("ProgenitorAlphaSpecialist")
        bravo = initialized_specialist_factory("ProgenitorBravoSpecialist")
        synthesizer = initialized_specialist_factory("TieredSynthesizerSpecialist")

        alpha.llm_adapter.invoke.return_value = {"text_response": "Alpha T1"}
        bravo.llm_adapter.invoke.return_value = {"text_response": "Bravo T1"}

        # Turn 1
        turn1_state = {"messages": [HumanMessage(content="Turn 1 question")]}

        # Simulate parallel execution
        alpha_result = alpha._execute_logic(turn1_state)
        bravo_result = bravo._execute_logic(turn1_state)

        # Merge artifacts (LangGraph would do this via reducer)
        turn1_artifacts = {
            "alpha_response": alpha_result["artifacts"]["alpha_response"],
            "bravo_response": bravo_result["artifacts"]["bravo_response"]
        }

        # Synthesizer combines
        synthesizer_result = synthesizer._execute_logic({
            "messages": turn1_state["messages"],
            "artifacts": turn1_artifacts
        })

        # Assert Turn 1: Clean history
        # progenitors did NOT add messages
        assert "messages" not in alpha_result
        assert "messages" not in bravo_result

        # Only synthesizer added 1 message
        assert len(synthesizer_result["messages"]) == 1

        # Turn 1 final state: 2 messages (user + synthesizer)
        turn1_final_messages = turn1_state["messages"] + synthesizer_result["messages"]
        assert len(turn1_final_messages) == 2

        # Turn 2
        turn2_state = {
            "messages": turn1_final_messages + [HumanMessage(content="Turn 2 question")]
        }

        alpha.llm_adapter.invoke.return_value = {"text_response": "Alpha T2"}
        bravo.llm_adapter.invoke.return_value = {"text_response": "Bravo T2"}

        alpha_result_t2 = alpha._execute_logic(turn2_state)
        bravo_result_t2 = bravo._execute_logic(turn2_state)

        turn2_artifacts = {
            "alpha_response": alpha_result_t2["artifacts"]["alpha_response"],
            "bravo_response": bravo_result_t2["artifacts"]["bravo_response"]
        }

        synthesizer_result_t2 = synthesizer._execute_logic({
            "messages": turn2_state["messages"],
            "artifacts": turn2_artifacts
        })

        # Assert Turn 2: Still clean history
        assert "messages" not in alpha_result_t2
        assert "messages" not in bravo_result_t2
        assert len(synthesizer_result_t2["messages"]) == 1

        # Turn 2 final state: 4 messages (user, synth, user, synth)
        turn2_final_messages = turn2_state["messages"] + synthesizer_result_t2["messages"]
        assert len(turn2_final_messages) == 4, (
            f"Expected 4 messages (clean history), got {len(turn2_final_messages)}. "
            "Bug behavior would result in 6+ messages from progenitor pollution."
        )

    def test_progenitors_receive_full_history_but_dont_pollute(self, initialized_specialist_factory):
        """
        Verifies progenitors READ full message history but DON'T WRITE to it.

        This is critical for cross-referencing: progenitors need to see the full
        conversation context, but should not append their individual responses to
        the permanent message history.
        """
        # Arrange
        alpha = initialized_specialist_factory("ProgenitorAlphaSpecialist")

        alpha.llm_adapter.invoke.return_value = {"text_response": "Response"}

        # Simulate multi-turn conversation with existing history
        state = {
            "messages": [
                HumanMessage(content="Turn 1"),
                AIMessage(content="Previous synthesized response", name="tiered_synthesizer_specialist"),
                HumanMessage(content="Turn 2 - follow up")
            ]
        }

        # Act
        result = alpha._execute_logic(state)

        # Assert
        # 1. Progenitor READS the full history (passes it to LLM)
        call_args = alpha.llm_adapter.invoke.call_args
        request = call_args[0][0]
        assert len(request.messages) == 3, "Progenitor should see full conversation history"

        # 2. Progenitor does NOT WRITE to messages
        assert "messages" not in result, "Progenitor must not pollute message history"

        # 3. Response goes to artifacts only
        assert "alpha_response" in result["artifacts"]
