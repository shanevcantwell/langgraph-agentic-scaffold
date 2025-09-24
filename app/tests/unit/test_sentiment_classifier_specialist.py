# Audited on Sept 23, 2025
# app/tests/unit/test_sentiment_classifier_specialist.py

from unittest.mock import MagicMock, patch
import pytest
from app.src.specialists.sentiment_classifier_specialist import SentimentClassifierSpecialist, Sentiment
from app.src.utils.errors import LLMInvocationError
from langchain_core.messages import AIMessage, HumanMessage

@pytest.fixture
def specialist():
    """Fixture for an initialized SentimentClassifierSpecialist."""
    s = SentimentClassifierSpecialist(specialist_name="sentiment_classifier_specialist", specialist_config={})
    s.llm_adapter = MagicMock()
    return s

@pytest.mark.parametrize("sentiment_value", ["positive", "negative", "neutral"])
def test_sentiment_classifier_specialist_execute_success(specialist, sentiment_value):
    # Arrange
    specialist.llm_adapter.invoke.return_value = {"json_response": {"sentiment": sentiment_value}}

    initial_state = {
        "messages": [HumanMessage(content="I love this!")]
    }

    # Act
    result_state = specialist.execute(initial_state)

    # Assert
    assert len(result_state["messages"]) == 1
    new_message = result_state["messages"][0]

    assert isinstance(new_message, AIMessage)
    assert sentiment_value in new_message.content
    assert new_message.name == "sentiment_classifier_specialist"
    assert result_state["artifacts"]["sentiment_analysis"]["sentiment"] == sentiment_value
    specialist.llm_adapter.invoke.assert_called_once()
    # Check that the last human message was passed to the LLM
    invoke_request = specialist.llm_adapter.invoke.call_args[0][0]
    assert "I love this!" in invoke_request.messages[-1].content

def test_sentiment_classifier_handles_invalid_sentiment_value(specialist):
    """Tests that the specialist self-corrects if the LLM returns an invalid sentiment value."""
    # Arrange
    specialist.llm_adapter.invoke.return_value = {"json_response": {"sentiment": "ambivalent"}}
    initial_state = {"messages": [HumanMessage(content="It was okay.")]}

    # Act
    result_state = specialist.execute(initial_state)

    # Assert
    assert "sentiment_analysis" not in result_state.get("artifacts", {})
    assert "LLM returned an invalid sentiment value" in result_state["messages"][0].content

@pytest.mark.parametrize("bad_response", [
    {"json_response": {"wrong_key": "positive"}},
    {"json_response": None},
    {"text_response": "some text"}
], ids=["wrong_key", "no_json", "text_response_instead"])
def test_sentiment_classifier_handles_malformed_llm_response(specialist, bad_response):
    """Tests that the specialist self-corrects if the LLM response is malformed."""
    # Arrange
    specialist.llm_adapter.invoke.return_value = bad_response
    initial_state = {"messages": [HumanMessage(content="Some text.")]}

    # Act
    result_state = specialist.execute(initial_state)

    # Assert
    assert "sentiment_analysis" not in result_state.get("artifacts", {})
    assert "Failed to get a valid sentiment classification" in result_state["messages"][0].content

def test_sentiment_classifier_handles_llm_invocation_error(specialist):
    """Tests that an LLMInvocationError is propagated."""
    # Arrange
    specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": [HumanMessage(content="Some text.")]}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        specialist.execute(initial_state)

@pytest.mark.parametrize("messages", [
    [],
    [AIMessage(content="An AI message.")]
], ids=["empty_list", "no_human_message"])
def test_sentiment_classifier_no_human_message_to_analyze(specialist, messages):
    """Tests that the specialist does not run if no HumanMessage is available."""
    # Arrange
    initial_state = {"messages": messages}

    # Act
    result_state = specialist.execute(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called()
    assert "No user message found to analyze" in result_state["messages"][0].content

def test_sentiment_classifier_uses_last_human_message(specialist):
    """Tests that the specialist specifically analyzes the last HumanMessage."""
    # Arrange
    specialist.llm_adapter.invoke.return_value = {"json_response": {"sentiment": "positive"}}
    initial_state = {
        "messages": [
            HumanMessage(content="This is old and bad."),
            AIMessage(content="Some AI response."),
            HumanMessage(content="This is new and good!")
        ]
    }

    # Act
    specialist.execute(initial_state)

    # Assert
    invoke_request = specialist.llm_adapter.invoke.call_args[0][0]
    assert "This is new and good!" in invoke_request.messages[-1].content
