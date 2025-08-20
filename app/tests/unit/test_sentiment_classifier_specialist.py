# app/tests/unit/test_sentiment_classifier_specialist.py

import unittest
from unittest.mock import MagicMock
from app.src.specialists.sentiment_classifier_specialist import SentimentClassifierSpecialist
from langchain_core.messages import AIMessage

class TestSentimentClassifierSpecialist(unittest.TestCase):

    def test_execute(self):
        # Arrange
        specialist = SentimentClassifierSpecialist()
        specialist.llm_adapter = MagicMock()
        specialist.llm_adapter.invoke.return_value = {"json_response": {"sentiment": "positive"}}

        initial_state = {
            "messages": [{"role": "user", "content": "I love this!"}]
        }

        # Act
        result_state = specialist.execute(initial_state)

        # Assert
        self.assertEqual(len(result_state["messages"]), 2)
        self.assertIsInstance(result_state["messages"][-1], AIMessage)
        self.assertIn("positive", result_state["messages"][-1].content)

if __name__ == '__main__':
    unittest.main()
