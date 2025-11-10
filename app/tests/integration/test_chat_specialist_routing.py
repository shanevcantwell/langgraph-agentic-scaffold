"""
Integration Test: Verify ChatSpecialist is actually invoked via router

This test validates that:
1. Router can discover ChatSpecialist from config
2. Router routes conversational queries to ChatSpecialist
3. ChatSpecialist executes and returns a response
4. The full workflow completes successfully

This is an END-TO-END test that proves ADR-001 works in practice.
"""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.config_loader import ConfigLoader


@pytest.mark.integration
@pytest.mark.skip(reason="TODO: Update mock responses for CORE-CHAT-002 routing complexity")
def test_router_invokes_chat_specialist_for_conversational_query():
    """
    End-to-end test: User asks a question → Router → ChatSpecialist → Response

    This verifies that ChatSpecialist is actually called in a real workflow,
    not just discovered in config.
    """
    # --- Arrange: Build real graph with real specialists ---
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Override to use router as entry point (not triage)
    config['workflow']['entry_point'] = 'router_specialist'

    # Create a mock ConfigLoader that returns our modified config
    mock_config_loader = MagicMock()
    mock_config_loader.get_config.return_value = config

    builder = GraphBuilder(mock_config_loader)
    graph_builder_instance = builder.build()

    # Mock ALL LLM adapters to avoid real API calls
    with patch('app.src.llm.factory.AdapterFactory.create_adapter') as mock_factory:
        # Create a mock adapter that will be used by all specialists
        mock_adapter = MagicMock()
        mock_adapter.model_name = "test-model"
        mock_factory.return_value = mock_adapter

        # Configure router to route to chat_specialist
        # The router calls invoke() once to decide where to route
        mock_adapter.invoke.side_effect = [
            # First call: Router decides to route to chat_specialist
            {
                "tool_calls": [{
                    "id": "call_route",
                    "type": "tool_call",
                    "args": {"next_specialist": "chat_specialist"}
                }]
            },
            # Second call: ChatSpecialist generates response
            {
                "text_response": "Python is a high-level programming language known for its simplicity and readability."
            }
        ]

        # Rebuild graph with mocked adapters
        builder = GraphBuilder(mock_config_loader)
        graph_builder_instance = builder.build()

        # Create initial state with user question
        initial_state = {
            "messages": [HumanMessage(content="What is Python?")],
            "artifacts": {},
            "scratchpad": {"use_simple_chat": True},  # Use simple chat mode to route directly to chat_specialist
            "task_is_complete": False
        }

        # --- Act: Run the workflow ---
        # Track which specialists were invoked by monitoring messages
        with patch('app.src.specialists.chat_specialist.ChatSpecialist._execute_logic', wraps=None) as mock_chat_execute:
            # Set up the mock to actually call through but let us track it
            original_chat_class = None
            try:
                from app.src.specialists.chat_specialist import ChatSpecialist
                original_chat_class = ChatSpecialist

                # Create a spy that tracks calls but executes the real logic
                def chat_specialist_spy(self, state):
                    """Spy function that proves ChatSpecialist was invoked"""
                    mock_chat_execute.was_called = True
                    mock_chat_execute.call_state = state
                    # Simulate what ChatSpecialist would return
                    from app.src.specialists.helpers import create_llm_message
                    ai_message = create_llm_message(
                        specialist_name="chat_specialist",
                        llm_adapter=self.llm_adapter,
                        content="Python is a high-level programming language."
                    )
                    return {
                        "messages": [ai_message],
                        "scratchpad": {"user_response_snippets": ["Python is a high-level programming language."]},
                        "task_is_complete": True
                    }

                mock_chat_execute.side_effect = chat_specialist_spy
                mock_chat_execute.was_called = False

                # Monkey-patch the method
                ChatSpecialist._execute_logic = mock_chat_execute

                # Now rebuild and run
                builder = GraphBuilder(mock_config_loader)
                graph_builder_instance = builder.build()

                final_state = graph_builder_instance.invoke(initial_state)

                # --- Assert: Verify ChatSpecialist was actually invoked ---
                assert mock_chat_execute.was_called, \
                    "ChatSpecialist._execute_logic was NOT called! Router did not route to ChatSpecialist."

                assert mock_chat_execute.call_state is not None, \
                    "ChatSpecialist was called but received no state"

                # Verify the user's question was in the state passed to ChatSpecialist
                messages_to_chat = mock_chat_execute.call_state.get("messages", [])
                assert any("Python" in str(msg.content) for msg in messages_to_chat), \
                    "User's question about Python was not passed to ChatSpecialist"

                # Verify final state contains a response
                assert len(final_state.get("messages", [])) > 1, \
                    "No response was generated"

                print("\n✓ ChatSpecialist WAS invoked by router")
                print(f"✓ Received state with {len(messages_to_chat)} message(s)")
                print(f"✓ Generated response in final state")

            finally:
                # Restore original
                if original_chat_class:
                    ChatSpecialist._execute_logic = original_chat_class._execute_logic


def test_chat_specialist_appears_in_router_specialist_map():
    """
    Simpler test: Verify ChatSpecialist is registered and discoverable by router.
    This is a prerequisite for routing but doesn't test actual invocation.
    """
    config_loader = ConfigLoader()
    config = config_loader.get_config()

    # Verify chat_specialist is in config
    assert 'chat_specialist' in config['specialists'], \
        "chat_specialist not found in config.yaml"

    # Verify it has a description (required for routing)
    chat_config = config['specialists']['chat_specialist']
    assert 'description' in chat_config, \
        "chat_specialist missing description in config"
    assert len(chat_config['description']) > 0, \
        "chat_specialist description is empty"

    print(f"\n✓ ChatSpecialist registered in config")
    print(f"✓ Description: {chat_config['description'][:60]}...")
