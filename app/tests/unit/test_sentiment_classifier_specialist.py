# app/tests/unit/test_sentiment_classifier_specialist.py

from unittest.mock import MagicMock
import pytest
from app.src.specialists.sentiment_classifier_specialist import SentimentClassifierSpecialist, Sentiment
from langchain_core.messages import AIMessage, HumanMessage

def test_sentiment_classifier_specialist_execute():
    # Arrange
    specialist = SentimentClassifierSpecialist("sentiment_classifier_specialist")
    specialist.llm_adapter = MagicMock()
    mock_sentiment = "positive"
    specialist.llm_adapter.invoke.return_value = {"json_response": {"sentiment": mock_sentiment}}

    initial_state = {
        "messages": [HumanMessage(content="I love this!")]
    }

    # Act
    # We test the public execute method, which is the entry point for the node.
    result_state = specialist.execute(initial_state)

    # Assert
    # The specialist should only return the *new* message it created.
    assert len(result_state["messages"]) == 1
    new_message = result_state["messages"][0]

    assert isinstance(new_message, AIMessage)
    assert mock_sentiment in new_message.content
    assert new_message.name == "sentiment_classifier_specialist"
    assert result_state["json_artifact"]["sentiment"] == mock_sentiment
