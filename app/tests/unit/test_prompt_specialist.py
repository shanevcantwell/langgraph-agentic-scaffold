import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import PromptSpecialist
from src.graph.state import GraphState

@pytest.fixture
def specialist_and_state():
    """Provides a PromptSpecialist instance and a default state."""
    specialist = PromptSpecialist(llm_provider="gemini")
    state = GraphState(messages=[HumanMessage(content="What should I do next?")])
    return specialist, state

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import PromptSpecialist
from src.graph.state import GraphState
import json

@pytest.fixture
def specialist_and_state():
    """Provides a PromptSpecialist instance and a default state."""
    specialist = PromptSpecialist(llm_provider="gemini")
    state = GraphState(messages=[HumanMessage(content="What should I do next?")])
    return specialist, state

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import PromptSpecialist
from src.graph.state import GraphState
import json

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import PromptSpecialist
from src.graph.state import GraphState
import json

@pytest.fixture
def default_state():
    """Provides a default state for tests."""
    return GraphState(messages=[HumanMessage(content="What should I do next?")])

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_prompt_specialist_happy_path(mock_create_client, default_state):
    """Tests that the specialist correctly processes a response and updates the state."""
    mock_client = MagicMock()
    # Simulate the LLM returning JSON wrapped in markdown code block delimiters
    expected_content = '```json\n{"response": "You should ask the file specialist to list files."}\n```'
    mock_client.invoke.return_value = AIMessage(content=expected_content)
    mock_create_client.return_value = mock_client

    specialist = PromptSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)

    # The specialist should add the LLM's response to the message history
    # Assert that the content of the AIMessage is exactly what was returned by the mock
    assert result["messages"][-1].content == expected_content
    assert isinstance(result["messages"][-1], AIMessage)

