import pytest
from unittest.mock import Mock, MagicMock
from app.src.specialists.image_specialist import ImageSpecialist


class TestImageSpecialist:
    """Test suite for ImageSpecialist - Vision capabilities via MCP."""

    def test_init(self, initialized_specialist_factory):
        """Test ImageSpecialist initializes correctly."""
        specialist = initialized_specialist_factory("ImageSpecialist")
        assert specialist is not None
        assert specialist.specialist_name == "image_specialist"
        assert isinstance(specialist, ImageSpecialist)

    def test_mcp_service_registration(self, initialized_specialist_factory):
        """Test that ImageSpecialist registers describe service via MCP."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock registry
        mock_registry = Mock()
        specialist.register_mcp_services(mock_registry)

        # Verify service registration
        mock_registry.register_service.assert_called_once()
        call_args = mock_registry.register_service.call_args

        assert call_args[0][0] == "image_specialist"
        services = call_args[0][1]
        assert "describe" in services
        assert callable(services["describe"])

    def test_describe_image_basic(self, initialized_specialist_factory):
        """Test basic image description via MCP."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "text_response": "A beautiful sunset over the ocean with orange and pink hues."
        }
        specialist.llm_adapter = mock_adapter

        # Test describe
        base64_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."
        description = specialist._describe_image(base64_image)

        assert description == "A beautiful sunset over the ocean with orange and pink hues."
        assert mock_adapter.invoke.called

        # Verify image data was passed
        request = mock_adapter.invoke.call_args[0][0]
        assert request.image_data == base64_image

    def test_describe_image_custom_prompt(self, initialized_specialist_factory):
        """Test image description with custom prompt."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "text_response": "The diagram shows a three-tier architecture."
        }
        specialist.llm_adapter = mock_adapter

        # Test with custom prompt
        base64_image = "data:image/png;base64,ABC123..."
        custom_prompt = "Analyze this architecture diagram in detail."
        description = specialist._describe_image(base64_image, custom_prompt)

        assert description == "The diagram shows a three-tier architecture."

        # Verify custom prompt was used
        request = mock_adapter.invoke.call_args[0][0]
        messages = request.messages
        assert any(custom_prompt in str(msg.content) for msg in messages)

    def test_describe_image_no_llm_adapter(self, initialized_specialist_factory):
        """Test that describe raises error if LLM adapter not attached."""
        specialist = initialized_specialist_factory("ImageSpecialist")
        specialist.llm_adapter = None

        with pytest.raises(ValueError, match="LLM Adapter not attached"):
            specialist._describe_image("data:image/png;base64,...")

    def test_describe_image_empty_response(self, initialized_specialist_factory):
        """Test handling of empty LLM response."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock adapter returning empty response
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {"text_response": ""}
        specialist.llm_adapter = mock_adapter

        description = specialist._describe_image("data:image/png;base64,...")

        assert "No description available" in description
        assert "empty response" in description

    def test_describe_image_llm_error(self, initialized_specialist_factory):
        """Test error handling when LLM invocation fails."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock adapter raising exception
        mock_adapter = Mock()
        mock_adapter.invoke.side_effect = Exception("Vision model timeout")
        specialist.llm_adapter = mock_adapter

        with pytest.raises(ValueError, match="Image analysis failed"):
            specialist._describe_image("data:image/png;base64,...")

    def test_execute_logic_with_uploaded_image(self, initialized_specialist_factory):
        """Test graph execution mode with uploaded image in artifacts."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "text_response": "Screenshot of a terminal window with green text."
        }
        specialist.llm_adapter = mock_adapter

        # Create state with uploaded image
        state = {
            "artifacts": {
                "uploaded_image.png": "data:image/png;base64,XYZ789..."
            }
        }

        result = specialist._execute_logic(state)

        assert "artifacts" in result
        assert "image_description" in result["artifacts"]
        assert result["artifacts"]["image_description"] == "Screenshot of a terminal window with green text."
        assert result["scratchpad"]["image_analysis_complete"] is True

    def test_execute_logic_with_image_to_process(self, initialized_specialist_factory):
        """Test graph execution mode with image_to_process artifact."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "text_response": "Flowchart showing decision tree."
        }
        specialist.llm_adapter = mock_adapter

        # Create state with image_to_process
        state = {
            "artifacts": {
                "image_to_process": "data:image/jpeg;base64,ABC456..."
            }
        }

        result = specialist._execute_logic(state)

        assert "artifacts" in result
        assert "image_description" in result["artifacts"]
        assert result["artifacts"]["image_description"] == "Flowchart showing decision tree."

    def test_execute_logic_with_custom_prompt_artifact(self, initialized_specialist_factory):
        """Test graph execution with custom analysis prompt in artifacts."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "text_response": "Technical specifications visible in diagram."
        }
        specialist.llm_adapter = mock_adapter

        # Create state with custom prompt
        state = {
            "artifacts": {
                "uploaded_image.png": "data:image/png;base64,DEF123...",
                "image_analysis_prompt": "Extract all technical specifications from this diagram."
            }
        }

        result = specialist._execute_logic(state)

        assert "image_description" in result["artifacts"]
        assert mock_adapter.invoke.called

    def test_execute_logic_no_image(self, initialized_specialist_factory):
        """Test graph execution returns error when no image in artifacts."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        specialist.llm_adapter = mock_adapter

        # State with no image
        state = {
            "artifacts": {}
        }

        result = specialist._execute_logic(state)

        assert "error" in result
        assert "No image to process" in result["error"]

    def test_execute_logic_no_llm_adapter(self, initialized_specialist_factory):
        """Test graph execution raises error if no LLM adapter."""
        specialist = initialized_specialist_factory("ImageSpecialist")
        specialist.llm_adapter = None

        state = {
            "artifacts": {
                "uploaded_image.png": "data:image/png;base64,..."
            }
        }

        with pytest.raises(ValueError, match="LLM Adapter not attached"):
            specialist._execute_logic(state)

    def test_execute_logic_describe_error(self, initialized_specialist_factory):
        """Test graph execution handles describe errors gracefully."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        # Mock adapter that raises exception
        mock_adapter = Mock()
        mock_adapter.invoke.side_effect = Exception("Model unavailable")
        specialist.llm_adapter = mock_adapter

        state = {
            "artifacts": {
                "uploaded_image.png": "data:image/png;base64,..."
            }
        }

        result = specialist._execute_logic(state)

        assert "error" in result
        assert "Image analysis failed" in result["error"]
        # BUG-SPECIALIST-001: Verify forbidden_specialists is set on failure
        assert "scratchpad" in result
        assert "forbidden_specialists" in result["scratchpad"]
        assert "image_specialist" in result["scratchpad"]["forbidden_specialists"]

    def test_execute_logic_success_sets_forbidden_specialists(self, initialized_specialist_factory):
        """Test that successful execution also sets forbidden_specialists (not me pattern)."""
        specialist = initialized_specialist_factory("ImageSpecialist")

        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {"text_response": "Test description"}
        specialist.llm_adapter = mock_adapter

        state = {
            "artifacts": {
                "uploaded_image.png": "data:image/png;base64,..."
            }
        }

        result = specialist._execute_logic(state)

        assert "artifacts" in result
        assert "scratchpad" in result
        assert "forbidden_specialists" in result["scratchpad"]
        assert "image_specialist" in result["scratchpad"]["forbidden_specialists"]
