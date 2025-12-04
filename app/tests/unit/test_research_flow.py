# app/tests/unit/test_research_flow.py
"""
Tests for the Research Flow behavior.

These tests capture bugs identified in the "Research the timeline of the Olde Boston Bulldogge breed"
failure case where:
1. DuckDuckGo returned "No Results" for a niche query
2. Router kept picking web_specialist in a loop
3. System terminated via loop detection instead of graceful failure reporting

Bug taxonomy:
- BUG-RESEARCH-001: Router doesn't see gathered_context content in LLM prompt
- BUG-RESEARCH-002: Router doesn't recognize "No Results" as failure state
- BUG-RESEARCH-003: web_specialist graph node called without scratchpad.web_task
- BUG-RESEARCH-004: Missing observability for Router input context
"""
import pytest
import logging
from unittest.mock import MagicMock, patch, call
from langchain_core.messages import HumanMessage, SystemMessage

from app.src.specialists.router_specialist import RouterSpecialist
from app.src.specialists.web_specialist import WebSpecialist
from app.src.strategies.search.duckduckgo_strategy import DuckDuckGoSearchStrategy
from app.src.graph.state_factory import create_test_state


# --- BUG-RESEARCH-001: Router Context Visibility ---

class TestRouterContextVisibility:
    """Router must pass gathered_context content to LLM for informed decision-making."""

    def test_router_llm_prompt_includes_gathered_context_content(self, initialized_specialist_factory):
        """
        BUG-RESEARCH-001: Router should include gathered_context CONTENT in LLM prompt.

        Currently router only checks IF gathered_context exists, but doesn't show
        the actual content to the LLM. This prevents the LLM from knowing that
        search returned "No Results".
        """
        # Arrange
        router = initialized_specialist_factory("RouterSpecialist")
        router.set_specialist_map({
            "web_specialist": {"description": "Web search", "tags": []},
            "chat_specialist": {"description": "General chat", "tags": []},
            "end_specialist": {"description": "End workflow", "tags": []}
        })

        # Simulate gathered_context with "No Results" from failed search
        gathered_context = """### Research: timeline of the Olde Boston Bulldogge breed
- [No Results](): No results found for query: timeline of the Olde Boston Bulldogge breed"""

        state = create_test_state(
            messages=[HumanMessage(content="Research the timeline of the Olde Boston Bulldogge breed")],
            artifacts={"gathered_context": gathered_context},
            scratchpad={},
            routing_history=["triage_architect", "facilitator_specialist"]
        )

        mock_adapter = router.llm_adapter
        mock_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "chat_specialist"}, "id": "call_123"}]
        }

        # Act
        router._get_llm_choice(state)

        # Assert: The LLM prompt should contain the actual gathered_context content
        call_args = mock_adapter.invoke.call_args
        request = call_args[0][0]

        # Find the prompt content
        prompt_content = " ".join([msg.content for msg in request.messages if hasattr(msg, 'content')])

        # BUG: Currently this will FAIL because Router doesn't include gathered_context content
        assert "No results found" in prompt_content or "No Results" in prompt_content, \
            "Router LLM prompt must include gathered_context content so it can see search failures"

    def test_router_logs_gathered_context_for_debugging(self, initialized_specialist_factory, caplog):
        """
        BUG-RESEARCH-004: Router should log what context it sees for debugging.

        When Router makes a decision, it should log the key artifacts it considered.
        """
        # Arrange
        router = initialized_specialist_factory("RouterSpecialist")
        router.set_specialist_map({
            "web_specialist": {"description": "Web search", "tags": []},
            "end_specialist": {"description": "End workflow", "tags": []}
        })

        gathered_context = "### Research: test query\n- [No Results](): No results"

        state = create_test_state(
            messages=[HumanMessage(content="Test")],
            artifacts={"gathered_context": gathered_context},
            scratchpad={},
            routing_history=[]
        )

        mock_adapter = router.llm_adapter
        mock_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "web_specialist"}, "id": "call_123"}]
        }

        # Act
        with caplog.at_level(logging.INFO):
            router._execute_logic(state)

        # Assert: Should log context information
        log_messages = [r.message for r in caplog.records]
        context_logged = any(
            "gathered_context" in msg.lower() or "context" in msg.lower()
            for msg in log_messages
        )

        # BUG: Currently Router only logs decision, not what context it saw
        # This makes debugging routing decisions very difficult
        assert context_logged, \
            "Router should log gathered_context info when making routing decisions"


# --- BUG-RESEARCH-002: Search Failure Recognition ---

class TestSearchFailureRecognition:
    """System must recognize and handle search failures gracefully."""

    def test_router_prompt_contains_failure_indicator_for_llm_decision(self, initialized_specialist_factory):
        """
        BUG-RESEARCH-002: Verify Router provides failure information to LLM.

        With BUG-RESEARCH-001 fixed, the Router now includes gathered_context in the
        LLM prompt. This test verifies the LLM receives enough information to recognize
        search failures and make informed routing decisions.

        Note: Whether the LLM actually avoids re-routing to failed specialists is an
        integration test concern. This unit test verifies the structural requirement
        that failure information IS visible in the prompt.
        """
        # Arrange
        router = initialized_specialist_factory("RouterSpecialist")
        router.set_specialist_map({
            "web_specialist": {"description": "Web search", "tags": []},
            "chat_specialist": {"description": "General response", "tags": []},
            "end_specialist": {"description": "End workflow", "tags": []}
        })

        # Context shows search already failed
        gathered_context = """### Research: Olde Boston Bulldogge timeline
- [No Results](): No results found for query: Olde Boston Bulldogge timeline"""

        state = create_test_state(
            messages=[HumanMessage(content="Research Olde Boston Bulldogge")],
            artifacts={"gathered_context": gathered_context},
            scratchpad={},
            routing_history=["triage_architect", "facilitator_specialist", "web_specialist"]
        )

        mock_adapter = router.llm_adapter
        mock_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "chat_specialist"}, "id": "call_123"}]
        }

        # Act
        router._get_llm_choice(state)

        # Assert: Verify the LLM prompt contains failure indicators
        call_args = mock_adapter.invoke.call_args
        request = call_args[0][0]
        prompt_content = " ".join([msg.content for msg in request.messages if hasattr(msg, 'content')])

        # The prompt must contain "No Results" so LLM can see the search failed
        assert "No Results" in prompt_content or "No results found" in prompt_content, \
            "Router prompt must include failure indicators from gathered_context"

        # The prompt must indicate context gathering is complete
        assert "CONTEXT GATHERING COMPLETE" in prompt_content, \
            "Router prompt must indicate context phase is done"

        # The prompt should show what context was gathered
        assert "GATHERED CONTEXT" in prompt_content, \
            "Router prompt must include gathered context section"

    def test_duckduckgo_no_results_returns_distinct_failure_marker(self):
        """
        Verify DuckDuckGoSearchStrategy returns a recognizable failure pattern.

        This is NOT a bug - the strategy correctly returns a "No Results" marker.
        This test documents the expected return format for failure detection.
        """
        # Arrange
        strategy = DuckDuckGoSearchStrategy()

        # Mock DDGS - it's lazy imported inside execute(), so patch the library directly
        with patch('duckduckgo_search.DDGS') as mock_ddgs:
            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
            mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
            mock_ddgs_instance.text.return_value = []  # Empty results
            mock_ddgs.return_value = mock_ddgs_instance

            from app.src.strategies.search.base import SearchRequest
            request = SearchRequest(query="obscure niche query")

            # Act
            results = strategy.execute(request)

        # Assert: Should return recognizable failure marker
        assert len(results) == 1
        assert results[0]["title"] == "No Results"
        assert "No results found" in results[0]["snippet"]

    def test_duckduckgo_rate_limit_retries_with_backoff(self):
        """
        Verify DuckDuckGoSearchStrategy retries on rate limit with exponential backoff.

        When DuckDuckGo rate limits us, the strategy should:
        1. Retry up to MAX_RETRIES times
        2. Wait with exponential backoff between attempts
        3. Return "Rate Limited" marker if all retries fail
        """
        from app.src.strategies.search.base import SearchRequest

        strategy = DuckDuckGoSearchStrategy()

        # Mock to simulate rate limiting
        with patch('duckduckgo_search.DDGS') as mock_ddgs, \
             patch('duckduckgo_search.exceptions.RatelimitException', Exception), \
             patch.object(strategy, 'INITIAL_BACKOFF_SECONDS', 0.01), \
             patch.object(strategy, 'MAX_RETRIES', 2):

            # Import actual exception after patching DDGS
            from duckduckgo_search.exceptions import RatelimitException

            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
            mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
            mock_ddgs_instance.text.side_effect = RatelimitException("202 Ratelimit")
            mock_ddgs.return_value = mock_ddgs_instance

            request = SearchRequest(query="test query")

            # Act
            results = strategy.execute(request)

        # Assert: Should return rate limited marker after retries exhausted
        assert len(results) == 1
        assert results[0]["title"] == "Rate Limited"
        assert "rate limited" in results[0]["snippet"].lower()

    def test_duckduckgo_rate_limit_succeeds_on_retry(self):
        """
        Verify DuckDuckGoSearchStrategy succeeds if retry works.
        """
        from app.src.strategies.search.base import SearchRequest
        from duckduckgo_search.exceptions import RatelimitException

        strategy = DuckDuckGoSearchStrategy()

        with patch('duckduckgo_search.DDGS') as mock_ddgs, \
             patch.object(strategy, 'INITIAL_BACKOFF_SECONDS', 0.01):

            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
            mock_ddgs_instance.__exit__ = MagicMock(return_value=False)

            # First call fails with rate limit, second succeeds
            mock_ddgs_instance.text.side_effect = [
                RatelimitException("202 Ratelimit"),
                [{"title": "Success", "href": "http://example.com", "body": "Found it"}]
            ]
            mock_ddgs.return_value = mock_ddgs_instance

            request = SearchRequest(query="test query")

            # Act
            results = strategy.execute(request)

        # Assert: Should succeed on retry
        assert len(results) == 1
        assert results[0]["title"] == "Success"
        assert results[0]["url"] == "http://example.com"


# --- BUG-RESEARCH-003: WebSpecialist Graph Node Invocation ---

class TestWebSpecialistInvocation:
    """WebSpecialist as graph node requires proper scratchpad setup."""

    def test_web_specialist_graph_node_requires_web_task(self):
        """
        BUG-RESEARCH-003: When Router routes to web_specialist, scratchpad.web_task
        must be set. Otherwise web_specialist._execute_logic() does nothing useful.

        Current flow:
        1. FacilitatorSpecialist calls web_specialist.search() via MCP - WORKS
        2. Router routes to web_specialist graph node - FAILS (no web_task)

        Router keeps routing to web_specialist but nobody sets up the task.
        """
        # Arrange
        specialist_config = {
            "description": "Web specialist",
            "llm_config": "test_config"
        }
        web_specialist = WebSpecialist("web_specialist", specialist_config, search_strategy=None)

        # State WITHOUT web_task (simulates what Router produces)
        state = create_test_state(
            messages=[HumanMessage(content="Research something")],
            scratchpad={},  # No web_task!
            routing_history=["router_specialist"]
        )

        # Act
        result = web_specialist._execute_logic(state)

        # Assert: Without web_task, specialist returns error
        assert "error" in result
        assert "No web_task found" in result["error"]

        # This documents the problem: Router routes to web_specialist but
        # nothing populates scratchpad.web_task, so web_specialist is a no-op

    def test_web_specialist_mcp_path_vs_graph_path(self):
        """
        Document the two invocation paths for WebSpecialist.

        Path 1 (MCP): FacilitatorSpecialist → mcp_client.call("web_specialist", "search", ...)
                      This correctly calls _perform_search() and returns results.

        Path 2 (Graph): Router → web_specialist node → _execute_logic()
                        This expects scratchpad.web_task which is never set.

        The bug is that Router routes to Path 2 expecting search to happen,
        but Path 2 requires explicit task setup that nobody provides.
        """
        # This test documents the architectural issue
        # The fix could be:
        # 1. Remove web_specialist from Router's menu (only callable via MCP)
        # 2. Have Router set scratchpad.web_task when routing to web_specialist
        # 3. Rename the graph node to clarify it's different from MCP service

        specialist_config = {"description": "Web specialist", "llm_config": "test"}

        # MCP path - exposes search function
        web_specialist = WebSpecialist("web_specialist", specialist_config, search_strategy=MagicMock())
        mock_registry = MagicMock()
        web_specialist.register_mcp_services(mock_registry)

        # Verify MCP registration
        mock_registry.register_service.assert_called_once()
        service_name, methods = mock_registry.register_service.call_args[0]
        assert service_name == "web_specialist"
        assert "search" in methods

        # Graph path - requires web_task
        state_without_task = create_test_state(scratchpad={})
        result = web_specialist._execute_logic(state_without_task)
        assert "error" in result  # Graph path fails without task


# --- Test Infrastructure ---

@pytest.fixture
def initialized_specialist_factory():
    """Factory for creating initialized specialists with mocked LLM."""
    def _factory(specialist_class_name: str):
        if specialist_class_name == "RouterSpecialist":
            config = {
                "description": "Routes requests",
                "llm_config": "test_config"
            }
            specialist = RouterSpecialist("router_specialist", config)
            specialist.llm_adapter = MagicMock()
            return specialist
        raise ValueError(f"Unknown specialist: {specialist_class_name}")
    return _factory


def setup_module(module):
    """Set up logging for the test module."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def teardown_module(module):
    """Teardown logging for the test module."""
    logging.shutdown()
