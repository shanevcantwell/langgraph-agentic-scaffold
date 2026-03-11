
import pytest
from unittest.mock import MagicMock, patch
from app.src.llm.local_inference_adapter import LocalInferenceAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage, SystemMessage

class TestImageInjection:
    def test_lmstudio_adapter_injects_image(self):
        # Setup
        config = {"api_identifier": "test-model", "base_url": "http://localhost:1234"}
        adapter = LocalInferenceAdapter(config, base_url="http://localhost:1234", system_prompt="sys")
        adapter.client = MagicMock()
        
        # Create request with image
        messages = [HumanMessage(content="Hello")]
        request = StandardizedLLMRequest(messages=messages, image_data="base64data")
        
        # Mock the client response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].message.tool_calls = None
        adapter.client.chat.completions.create.return_value = mock_response
        
        # Invoke
        adapter.invoke(request)
        
        # Verify
        call_args = adapter.client.chat.completions.create.call_args
        api_kwargs = call_args[1]
        sent_messages = api_kwargs["messages"]
        
        # The last message (user) should be multimodal
        last_msg = sent_messages[-1]
        assert last_msg["role"] == "user"
        assert isinstance(last_msg["content"], list)
        assert last_msg["content"][0]["type"] == "text"
        assert last_msg["content"][0]["text"] == "Hello"
        assert last_msg["content"][1]["type"] == "image_url"
        assert last_msg["content"][1]["image_url"]["url"] == "data:image/png;base64,base64data"

    def test_lmstudio_adapter_no_image(self):
        # Setup
        config = {"api_identifier": "test-model", "base_url": "http://localhost:1234"}
        adapter = LocalInferenceAdapter(config, base_url="http://localhost:1234", system_prompt="sys")
        adapter.client = MagicMock()
        
        # Create request WITHOUT image
        messages = [HumanMessage(content="Hello")]
        request = StandardizedLLMRequest(messages=messages, image_data=None)
        
        # Mock response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Response"
        mock_response.choices[0].message.tool_calls = None
        adapter.client.chat.completions.create.return_value = mock_response
        
        # Invoke
        adapter.invoke(request)
        
        # Verify
        call_args = adapter.client.chat.completions.create.call_args
        api_kwargs = call_args[1]
        sent_messages = api_kwargs["messages"]
        
        # The last message should be text only
        last_msg = sent_messages[-1]
        assert last_msg["role"] == "user"
        assert last_msg["content"] == "Hello"
