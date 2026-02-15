# app/tests/integration/test_specialist_execution.py
"""
Comprehensive execution tests for all specialists.

Tests that each specialist:
1. Loads and initializes successfully
2. Executes and produces expected output format
3. Sets appropriate state fields
4. Handles edge cases gracefully

Uses mocked LLM adapters to control specialist outputs while testing
actual specialist logic.
"""
import pytest
from unittest.mock import MagicMock, patch
import json

from app.src.graph.state_factory import create_test_state
from langchain_core.messages import HumanMessage, AIMessage


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_llm_response():
    """Factory for creating mock LLM responses."""
    def _create_response(text_response: str = None, json_response=None, tool_calls=None):
        response = {}
        if text_response:
            response["text_response"] = text_response
        if json_response:
            response["json_response"] = json_response
        if tool_calls:
            response["tool_calls"] = tool_calls
        return response
    return _create_response


@pytest.fixture
def base_state():
    """Create base test state with minimal required fields."""
    return create_test_state(
        messages=[HumanMessage(content="Test input")]
    )


# =============================================================================
# SYSTEMS ARCHITECT TESTS
# =============================================================================

class TestSystemsArchitectExecution:
    """Test SystemsArchitect specialist execution."""

    def test_systems_architect_produces_system_plan(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify SystemsArchitect creates system_plan artifact."""
        architect = initialized_specialist_factory("SystemsArchitect")

        # Mock LLM to return valid plan as json_response (matches SystemPlan schema)
        plan_data = {
            "plan_summary": "Build a test REST API with authentication",
            "required_components": ["FastAPI", "PostgreSQL", "JWT library"],
            "execution_steps": ["Set up database", "Create API endpoints", "Add auth"]
        }
        architect.llm_adapter.invoke.return_value = mock_llm_response(json_response=plan_data)

        # Execute
        result = architect.execute(base_state)

        # Verify artifacts contain system_plan
        assert "artifacts" in result
        assert "system_plan" in result["artifacts"]

    def test_systems_architect_raises_on_missing_json(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify SystemsArchitect raises error when json_response missing."""
        architect = initialized_specialist_factory("SystemsArchitect")

        # Mock LLM to return text_response only (no json_response)
        architect.llm_adapter.invoke.return_value = mock_llm_response(text_response="Invalid")

        # Should raise error
        with pytest.raises(Exception):
            architect.execute(base_state)


# =============================================================================
# WEB BUILDER TESTS
# =============================================================================

class TestWebBuilderExecution:
    """Test WebBuilder specialist execution."""

    def test_web_builder_produces_html_artifact(
        self, initialized_specialist_factory, mock_llm_response
    ):
        """Verify WebBuilder creates HTML artifact."""
        builder = initialized_specialist_factory("WebBuilder")

        # Create state with system_plan artifact
        state = create_test_state(
            messages=[HumanMessage(content="Build a contact form")],
            artifacts={
                "system_plan": {
                    "project_name": "Contact Form",
                    "components": [{"name": "Form", "description": "Contact form"}]
                }
            }
        )

        # Mock LLM to return WebContent schema (json_response with html_document)
        web_content_data = {
            "html_document": """<!DOCTYPE html>
<html>
<head><title>Contact Form</title></head>
<body>
    <form>
        <input type="text" name="name" placeholder="Name">
        <input type="email" name="email" placeholder="Email">
        <button type="submit">Submit</button>
    </form>
</body>
</html>"""
        }
        builder.llm_adapter.invoke.return_value = mock_llm_response(json_response=web_content_data)

        # Execute
        result = builder.execute(state)

        # Verify artifacts contain HTML
        assert "artifacts" in result
        assert "html_document.html" in result["artifacts"]


# =============================================================================
# CHAT SPECIALIST TESTS
# =============================================================================

class TestChatSpecialistExecution:
    """Test ChatSpecialist execution."""

    def test_chat_specialist_produces_response(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify ChatSpecialist produces conversational response."""
        chat = initialized_specialist_factory("ChatSpecialist")

        chat.llm_adapter.invoke.return_value = mock_llm_response(
            "Python is a high-level programming language known for its readability."
        )

        result = chat.execute(base_state)

        # Should produce messages or artifacts
        assert result is not None
        assert "messages" in result or "artifacts" in result


# =============================================================================
# TEXT ANALYSIS SPECIALIST TESTS
# =============================================================================

class TestTextAnalysisSpecialistExecution:
    """Test TextAnalysisSpecialist execution."""

    def test_text_analysis_summarizes_content(
        self, initialized_specialist_factory, mock_llm_response
    ):
        """Verify TextAnalysisSpecialist summarizes text content."""
        analyst = initialized_specialist_factory("TextAnalysisSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="Summarize the following document")],
            artifacts={"text_to_process": "Long document content here..." * 100}
        )

        # TextAnalysis schema requires summary and main_points
        analysis_data = {
            "summary": "This document discusses several key topics including...",
            "main_points": ["Point 1: Overview", "Point 2: Details", "Point 3: Conclusion"]
        }
        analyst.llm_adapter.invoke.return_value = mock_llm_response(json_response=analysis_data)

        result = analyst.execute(state)
        assert result is not None


# =============================================================================
# BATCH PROCESSOR TESTS
# =============================================================================

class TestBatchProcessorExecution:
    """Test BatchProcessorSpecialist execution."""

    def test_batch_processor_initializes(
        self, initialized_specialist_factory
    ):
        """Verify BatchProcessorSpecialist initializes correctly."""
        processor = initialized_specialist_factory("BatchProcessorSpecialist")
        assert processor is not None
        assert processor.specialist_name == "batch_processor_specialist"


# =============================================================================
# SUMMARIZER SPECIALIST TESTS
# =============================================================================

class TestSummarizerSpecialistExecution:
    """Test SummarizerSpecialist execution."""

    def test_summarizer_produces_summary(
        self, initialized_specialist_factory, mock_llm_response
    ):
        """Verify SummarizerSpecialist produces text summary."""
        summarizer = initialized_specialist_factory("SummarizerSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="Summarize this")],
            artifacts={"text_to_process": "Very long text " * 500}
        )

        summarizer.llm_adapter.invoke.return_value = mock_llm_response(
            "This text can be summarized as follows: ..."
        )

        result = summarizer.execute(state)
        assert result is not None


# =============================================================================
# PROMPT SPECIALIST TESTS
# =============================================================================

class TestPromptSpecialistExecution:
    """Test PromptSpecialist execution."""

    def test_prompt_specialist_generates_prompt(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify PromptSpecialist generates improved prompts."""
        prompt_spec = initialized_specialist_factory("PromptSpecialist")

        prompt_spec.llm_adapter.invoke.return_value = mock_llm_response(
            "Here's an improved prompt: 'Please analyze the code structure and provide detailed documentation including function descriptions and usage examples.'"
        )

        result = prompt_spec.execute(base_state)
        assert result is not None


# =============================================================================
# DEFAULT RESPONDER TESTS
# =============================================================================

class TestDefaultResponderExecution:
    """Test DefaultResponderSpecialist execution."""

    def test_default_responder_handles_greeting(
        self, initialized_specialist_factory, mock_llm_response
    ):
        """Verify DefaultResponder handles simple greetings."""
        responder = initialized_specialist_factory("DefaultResponderSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="Hello!")]
        )

        responder.llm_adapter.invoke.return_value = mock_llm_response(
            "Hello! How can I help you today?"
        )

        result = responder.execute(state)
        assert result is not None


# =============================================================================
# PROGENITOR SPECIALISTS TESTS
# =============================================================================

class TestProgenitorSpecialistsExecution:
    """Test Progenitor Alpha and Bravo specialists execution."""

    def test_progenitor_alpha_produces_artifact(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify ProgenitorAlpha writes to artifacts, not messages."""
        alpha = initialized_specialist_factory("ProgenitorAlphaSpecialist")

        alpha.llm_adapter.invoke.return_value = mock_llm_response(
            "From an analytical perspective, this topic involves..."
        )

        result = alpha.execute(base_state)

        # Progenitors should write to artifacts (parallel node pattern)
        assert "artifacts" in result
        assert "alpha_response.md" in result["artifacts"]
        # Should NOT write to messages (parallel node constraint)
        assert "messages" not in result or len(result.get("messages", [])) == 0

    def test_progenitor_bravo_produces_artifact(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify ProgenitorBravo writes to artifacts, not messages."""
        bravo = initialized_specialist_factory("ProgenitorBravoSpecialist")

        bravo.llm_adapter.invoke.return_value = mock_llm_response(
            "From an intuitive perspective, this feels like..."
        )

        result = bravo.execute(base_state)

        # Progenitors should write to artifacts (parallel node pattern)
        assert "artifacts" in result
        assert "bravo_response.md" in result["artifacts"]
        # Should NOT write to messages (parallel node constraint)
        assert "messages" not in result or len(result.get("messages", [])) == 0


# =============================================================================
# TIERED SYNTHESIZER TESTS
# =============================================================================

class TestTieredSynthesizerExecution:
    """Test TieredSynthesizerSpecialist execution."""

    def test_synthesizer_combines_progenitor_responses(
        self, initialized_specialist_factory
    ):
        """Verify TieredSynthesizer combines alpha and bravo responses."""
        synthesizer = initialized_specialist_factory("TieredSynthesizerSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="What is recursion?")],
            artifacts={
                "alpha_response.md": "Analytically, recursion is a function calling itself...",
                "bravo_response.md": "Intuitively, recursion is like looking into mirrors facing each other..."
            }
        )

        result = synthesizer.execute(state)

        # Synthesizer should write to messages (join node)
        assert "messages" in result or "artifacts" in result


# =============================================================================
# TRIAGE ARCHITECT TESTS
# =============================================================================

class TestTriageArchitectExecution:
    """Test TriageArchitect execution."""

    def test_triage_architect_writes_scratchpad(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify TriageArchitect writes triage_actions and triage_reasoning to scratchpad."""
        triage = initialized_specialist_factory("TriageArchitect")

        plan_response = json.dumps({
            "actions": [
                {"type": "research", "target": "Python 3.12 features", "description": "Research latest features"}
            ],
            "reasoning": "User wants to know about Python 3.12 features"
        })
        triage.llm_adapter.invoke.return_value = mock_llm_response(plan_response)

        result = triage.execute(base_state)

        assert result is not None
        scratchpad = result.get("scratchpad", {})
        assert "triage_reasoning" in scratchpad
        assert "triage_actions" in scratchpad


# =============================================================================
# ROUTER SPECIALIST TESTS
# =============================================================================

class TestRouterSpecialistExecution:
    """Test RouterSpecialist execution."""

    def test_router_produces_routing_decision(
        self, initialized_specialist_factory, mock_llm_response, base_state
    ):
        """Verify RouterSpecialist produces routing decision."""
        router = initialized_specialist_factory("RouterSpecialist")

        # Mock tool call response for routing
        router.llm_adapter.invoke.return_value = {
            "text_response": "",
            "tool_calls": [
                {
                    "name": "route_to_specialist",
                    "args": {"specialist_name": "chat_specialist"}
                }
            ]
        }

        result = router.execute(base_state)

        # Router should update scratchpad with routing decision
        assert result is not None


# =============================================================================
# ARCHIVER SPECIALIST TESTS
# =============================================================================

class TestArchiverSpecialistExecution:
    """Test ArchiverSpecialist execution."""

    def test_archiver_creates_archive_package(
        self, initialized_specialist_factory, tmp_path
    ):
        """Verify ArchiverSpecialist creates an Atomic Archival Package."""
        import os
        from pathlib import Path

        # Set archive path to temp directory
        os.environ["AGENTIC_SCAFFOLD_ARCHIVE_PATH"] = str(tmp_path)

        archiver = initialized_specialist_factory("ArchiverSpecialist")

        state = create_test_state(
            messages=[
                HumanMessage(content="What is Python?"),
                AIMessage(content="Python is a programming language...")
            ],
            artifacts={
                "final_user_response.md": "Python is a versatile programming language.",
                "response_mode": "tiered_full"
            }
        )
        state["routing_history"] = ["triage_architect", "chat_specialist", "end_specialist"]

        result = archiver.execute(state)

        # Should produce archive_package_path artifact
        assert "artifacts" in result
        assert "archive_package_path" in result["artifacts"]

        # Verify archive file was created
        archive_path = result["artifacts"]["archive_package_path"]
        assert Path(archive_path).exists(), f"Archive not created at {archive_path}"
        assert archive_path.endswith(".zip")

    def test_archiver_includes_manifest(
        self, initialized_specialist_factory, tmp_path
    ):
        """Verify archive includes valid manifest.json."""
        import os
        import zipfile
        import json

        os.environ["AGENTIC_SCAFFOLD_ARCHIVE_PATH"] = str(tmp_path)

        archiver = initialized_specialist_factory("ArchiverSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="Test")],
            artifacts={"final_user_response.md": "Test response"}
        )
        state["routing_history"] = ["triage_architect", "end_specialist"]

        result = archiver.execute(state)

        archive_path = result["artifacts"]["archive_package_path"]

        # Open and verify manifest
        with zipfile.ZipFile(archive_path, 'r') as zf:
            assert "manifest.json" in zf.namelist()

            manifest = json.loads(zf.read("manifest.json"))
            assert "run_id" in manifest
            assert "routing_history" in manifest
            assert "final_response_generated" in manifest

    def test_archiver_includes_report(
        self, initialized_specialist_factory, tmp_path
    ):
        """Verify archive includes report.md."""
        import os
        import zipfile

        os.environ["AGENTIC_SCAFFOLD_ARCHIVE_PATH"] = str(tmp_path)

        archiver = initialized_specialist_factory("ArchiverSpecialist")

        state = create_test_state(
            messages=[HumanMessage(content="Generate a report")],
            artifacts={"final_user_response.md": "Here is your report content."}
        )
        state["routing_history"] = ["triage_architect", "chat_specialist", "end_specialist"]

        result = archiver.execute(state)

        archive_path = result["artifacts"]["archive_package_path"]

        with zipfile.ZipFile(archive_path, 'r') as zf:
            assert "report.md" in zf.namelist()

            report_content = zf.read("report.md").decode("utf-8")
            # Report should have some content
            assert len(report_content) > 0


# =============================================================================
# END SPECIALIST TESTS
# =============================================================================

class TestEndSpecialistExecution:
    """Test EndSpecialist execution."""

    def test_end_specialist_synthesizes_response(
        self, initialized_specialist_factory, mock_llm_response
    ):
        """Verify EndSpecialist synthesizes final response."""
        end = initialized_specialist_factory("EndSpecialist")

        state = create_test_state(
            messages=[
                HumanMessage(content="What is Python?"),
                AIMessage(content="Python is a programming language...")
            ],
            artifacts={"some_artifact": "artifact content"}
        )

        end.llm_adapter.invoke.return_value = mock_llm_response(
            "Based on our conversation, Python is a versatile programming language..."
        )

        result = end.execute(state)

        # Should produce final_user_response
        assert result is not None


# =============================================================================
# SPECIALIST LOADING TESTS
# =============================================================================

class TestSpecialistLoading:
    """Test that all specialists load without errors."""

    SPECIALIST_CLASSES = [
        "SystemsArchitect",
        "WebBuilder",
        "ChatSpecialist",
        # "SentimentClassifierSpecialist",  # Removed in Issue #82
        "TextAnalysisSpecialist",
        "BatchProcessorSpecialist",
        # "ResearcherSpecialist",  # Removed in Phase 1
        "SummarizerSpecialist",
        "PromptSpecialist",
        "DefaultResponderSpecialist",
        "ProgenitorAlphaSpecialist",
        "ProgenitorBravoSpecialist",
        "TieredSynthesizerSpecialist",
        "TriageArchitect",
        "RouterSpecialist",
        "DataExtractorSpecialist",
        "ImageSpecialist",
    ]

    @pytest.mark.parametrize("class_name", SPECIALIST_CLASSES)
    def test_specialist_loads_successfully(
        self, initialized_specialist_factory, class_name
    ):
        """Verify specialist class loads without errors."""
        try:
            specialist = initialized_specialist_factory(class_name)
            assert specialist is not None
            assert hasattr(specialist, 'execute')
            assert hasattr(specialist, 'specialist_name')
        except Exception as e:
            pytest.fail(f"Failed to load {class_name}: {e}")
