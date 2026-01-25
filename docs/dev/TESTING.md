# How to Write Integration Tests

> **CRITICAL: ALWAYS RUN TESTS IN DOCKER**
>
> Integration tests **MUST** be run inside the Docker container. Running them locally will fail due to environment mismatches, network configuration issues, and missing dependencies.
>
> **Correct Command:**
> ```bash
> docker exec langgraph-app pytest app/tests/integration/
> ```
> **NEVER** run `pytest` directly in your local shell for integration tests.
> **NEVER** use `docker compose run` - it creates zombie containers that persist after completion.

This guide provides a step-by-step walkthrough for writing integration tests for the langgraph-agentic-scaffold. It is intended for developers who want to add comprehensive test coverage beyond unit tests.

## Introduction: What Are Integration Tests?

Integration tests validate that multiple components work together correctly in real-world scenarios. Unlike unit tests that mock dependencies, integration tests use real config files, real specialists, and real workflows to catch issues that unit tests miss.

**Why They Matter**: The critique_strategy config error exposed a critical gap - unit tests with mocked fixtures don't validate that real config files are correct. Integration tests catch configuration errors, contract mismatches, and state pollution bugs.

---

## Current Integration Test Coverage

Before writing new tests, check what's already covered in `app/tests/integration/`:

| Area | Test File | What It Validates |
|------|-----------|-------------------|
| **Config Loading** | `test_config_validation.py` | Real config.yaml loads, specialist configs valid |
| **Chat Routing** | `test_chat_specialist_routing.py` | End-to-end routing from user → Router → ChatSpecialist |
| **Gradio/API** | `test_gradio_integration.py` | API client connection, streaming, error handling |
| **Live LLMs** | `test_live_llm.py`, `test_live_lmstudio.py` | Real API calls to Gemini and LMStudio |
| **Workflows** | `test_plan_and_execute_integration.py` | Full workflow execution and failure handling |

---

## Step 1: Choose the Right Test Type

### When to Write an Integration Test

✅ **Write integration tests when:**
- Testing cross-component interactions (e.g., Router → Specialist → Archiver)
- Validating config file correctness
- Testing artifact passing between specialists
- Validating state transitions through workflows
- Testing error recovery paths

❌ **Don't write integration tests for:**
- Single component logic (use unit tests)
- Testing mock behavior (defeats the purpose)
- Trivial getters/setters

---

## Step 2: Set Up Your Test File

### File Location and Naming

Integration tests go in `app/tests/integration/` and follow the naming pattern `test_<feature>_integration.py`.

```python
# app/tests/integration/test_mcp_service_integration.py

import pytest
from app.src.workflow.graph_builder import GraphBuilder
from app.src.config.loader import ConfigLoader
from app.src.mcp.client import McpClient

class TestMcpServiceIntegration:
    """Integration tests for MCP service registration and invocation."""

    def test_file_reader_service_registers_and_responds(self):
        """Validates FileReaderService registers and can be called via McpClient."""
        # Test implementation here
        pass
```

### Use Real Components, Not Mocks

**❌ Bad - Mocking defeats integration testing:**
```python
mock_config = {"specialists": {"critic": {...}}}
builder = GraphBuilder(config_loader=mock_config_loader)
```

**✅ Good - Use real config:**
```python
config_loader = ConfigLoader()  # Loads actual config.yaml
builder = GraphBuilder(config_loader=config_loader)
specialist = builder.specialists["critic_specialist"]
```

---

## Step 3: Write Configuration Validation Tests

### Example: Validate Specialist Configuration

```python
def test_all_specialists_load_from_config(self):
    """Validates all specialists in config.yaml load without errors."""
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)

    # Should not raise any errors
    graph = builder.build()

    # Verify critical specialists loaded
    assert "router_specialist" in builder.specialists
    assert "archiver_specialist" in builder.specialists
```

### Example: Validate Required Fields

```python
def test_critic_specialist_has_critique_strategy(self):
    """Validates critic_specialist config includes required critique_strategy."""
    config_loader = ConfigLoader()
    config = config_loader.load_config()

    critic_config = config["specialists"]["critic_specialist"]
    assert "critique_strategy" in critic_config
    assert critic_config["critique_strategy"] in ["iterative", "comparative"]
```

---

## Step 4: Write End-to-End Workflow Tests

### Example: Full Routing Flow

```python
def test_user_query_routes_to_chat_specialist(self):
    """End-to-end: User query → Router → ChatSpecialist → Response."""
    # Build real graph
    config_loader = ConfigLoader()
    builder = GraphBuilder(config_loader=config_loader)
    graph = builder.build()

    # Execute workflow
    initial_state = {
        "messages": [HumanMessage(content="Hello, how are you?")],
        "artifacts": {},
        "scratchpad": {}
    }

    result = graph.invoke(initial_state)

    # Verify routing occurred
    assert len(result["messages"]) > 1  # Router + ChatSpecialist responded
    assert "routing_history" in result["scratchpad"]
    assert "chat_specialist" in result["scratchpad"]["routing_history"]
```

### Example: Artifact Passing

```python
def test_systems_architect_produces_plan_for_web_builder(self):
    """Validates artifact flow: SystemsArchitect → WebBuilder."""
    builder = GraphBuilder(config_loader=ConfigLoader())
    graph = builder.build()

    initial_state = {
        "messages": [HumanMessage(content="Create a login page")],
        "artifacts": {},
        "scratchpad": {}
    }

    result = graph.invoke(initial_state)

    # Verify artifact was created
    assert "system_plan" in result["artifacts"]

    # Verify WebBuilder consumed it
    assert "html_output" in result["artifacts"]
```

---

## Step 5: Write MCP Service Tests

### Example: Service Registration

```python
def test_file_reader_service_registers_correctly(self):
    """Validates FileReaderService registers its methods with MCP registry."""
    from app.src.specialists.file_specialist import FileSpecialist
    from app.src.mcp.registry import McpRegistry

    registry = McpRegistry()
    specialist = FileSpecialist("file_specialist", config={})

    # Register services
    specialist.register_mcp_services(registry)

    # Verify services registered
    assert registry.has_service("file_reader", "read_file")
    assert registry.has_service("file_reader", "file_exists")
    assert registry.has_service("file_reader", "list_files")
```

### Example: Service Invocation

```python
def test_mcp_client_calls_file_reader_service(self):
    """Validates McpClient can discover and call FileReaderService."""
    registry = McpRegistry()
    client = McpClient(registry)

    # Register file reader
    file_specialist = FileSpecialist("file_specialist", config={})
    file_specialist.register_mcp_services(registry)

    # Call service via MCP
    result = client.call(
        service_name="file_reader",
        function_name="file_exists",
        parameters={"path": "config.yaml"}
    )

    assert result.status == "success"
    assert result.data["exists"] is True
```

---

## Step 6: Write State Lifecycle Tests

### Example: Scratchpad Cleanup

```python
def test_scratchpad_cleared_after_routing(self):
    """Validates scratchpad is cleaned after router decision."""
    builder = GraphBuilder(config_loader=ConfigLoader())
    graph = builder.build()

    initial_state = {
        "messages": [HumanMessage(content="Test message")],
        "artifacts": {},
        "scratchpad": {"test_data": "should be cleared"}
    }

    result = graph.invoke(initial_state)

    # Scratchpad should be cleaned of temporary data
    assert "test_data" not in result["scratchpad"]
```

### Example: Message Accumulation

```python
def test_messages_accumulate_through_conversation(self):
    """Validates conversation history grows correctly over multiple turns."""
    builder = GraphBuilder(config_loader=ConfigLoader())
    graph = builder.build()

    # First turn
    state = {
        "messages": [HumanMessage(content="Hello")],
        "artifacts": {},
        "scratchpad": {}
    }

    result1 = graph.invoke(state)
    turn1_message_count = len(result1["messages"])

    # Second turn (append to history)
    result1["messages"].append(HumanMessage(content="Follow-up question"))
    result2 = graph.invoke(result1)

    # History should grow
    assert len(result2["messages"]) > turn1_message_count
```

---

## Step 7: Write Error Handling Tests

### Example: Graceful Failure

```python
def test_specialist_handles_missing_artifact_gracefully(self):
    """Validates specialist raises clear error when required artifact missing."""
    builder = GraphBuilder(config_loader=ConfigLoader())
    specialist = builder.specialists["web_builder"]

    # State without required artifact
    state = {
        "messages": [HumanMessage(content="Build a page")],
        "artifacts": {},  # Missing "system_plan" artifact
        "scratchpad": {}
    }

    result = specialist.execute(state)

    # Should produce error, not crash
    assert result["error_report"] is not None
    assert "Required artifact" in result["error_report"]
```

### Example: Degradation Mode

```python
def test_tiered_chat_graceful_degradation_alpha_only(self):
    """Validates tiered chat falls back gracefully when Bravo fails."""
    # Temporarily disable Bravo progenitor
    config_loader = ConfigLoader()
    config = config_loader.load_config()
    config["specialists"]["progenitor_bravo"]["enabled"] = False

    builder = GraphBuilder(config_loader=config_loader)
    graph = builder.build()

    state = {
        "messages": [HumanMessage(content="Test question")],
        "artifacts": {},
        "scratchpad": {}
    }

    result = graph.invoke(state)

    # Should use degradation mode
    assert result["artifacts"]["response_mode"] == "tiered_alpha_only"
    assert len(result["messages"]) > 1  # Still got a response
```

---

## Step 8: Run and Debug Integration Tests

### Running Tests

```bash
# Run all integration tests
docker compose exec app python -m pytest app/tests/integration/ -v

# Run specific test file
docker compose exec app python -m pytest app/tests/integration/test_mcp_service_integration.py -v

# Run specific test function
docker compose exec app python -m pytest app/tests/integration/test_mcp_service_integration.py::TestMcpServiceIntegration::test_file_reader_service_registers_correctly -v
```

### Debugging Failed Tests

**Use verbose output:**
```bash
pytest app/tests/integration/test_your_feature.py -vv -s
```

**Check logs:**
```bash
# View application logs
cat logs/agentic_server.log

# View test output with print statements
pytest app/tests/integration/test_your_feature.py -s
```

**Add breakpoints:**
```python
def test_something(self):
    # Add breakpoint for debugging
    import pdb; pdb.set_trace()

    result = graph.invoke(state)
    assert result is not None
```

---

## Common Integration Test Patterns

### Pattern 1: Config-Driven Tests

```python
@pytest.mark.parametrize("specialist_name", [
    "router_specialist",
    "chat_specialist",
    "file_specialist",
    "archiver_specialist"
])
def test_specialist_loads_from_config(specialist_name):
    """Validates each specialist loads correctly from config."""
    builder = GraphBuilder(config_loader=ConfigLoader())
    assert specialist_name in builder.specialists
```

### Pattern 2: Workflow State Assertions

```python
def test_workflow_state_transitions(self):
    """Validates state transitions through complete workflow."""
    graph = GraphBuilder(config_loader=ConfigLoader()).build()

    initial = create_initial_state("Test prompt")
    result = graph.invoke(initial)

    # Assert expected state transitions
    assert_routing_occurred(result)
    assert_artifacts_created(result)
    assert_task_completed(result)
```

### Pattern 3: Service Contract Tests

```python
def test_mcp_service_contract(self):
    """Validates MCP service request/response contract."""
    client = McpClient(registry)

    request = McpRequest(
        service_name="file_reader",
        function_name="read_file",
        parameters={"path": "test.txt"}
    )

    response = client.execute(request)

    # Validate response contract
    assert isinstance(response, McpResponse)
    assert response.request_id == request.request_id
    assert response.status in ["success", "error"]
```

---

## Anti-Patterns to Avoid

### ❌ Don't Mock Everything

```python
# BAD: Defeats purpose of integration testing
mock_config = MagicMock()
mock_specialist = MagicMock()
result = mock_specialist.execute(mock_state)
```

### ✅ Use Real Components

```python
# GOOD: Tests real integration
config = ConfigLoader().load_config()
specialist = GraphBuilder().specialists["real_specialist"]
result = specialist.execute(real_state)
```

### ❌ Don't Test Only Happy Paths

```python
# BAD: Only tests success
def test_specialist_works():
    result = specialist.execute(state)
    assert result is not None
```

### ✅ Test Error Paths Too

```python
# GOOD: Tests both success and failure
def test_specialist_handles_errors():
    # Test success
    result = specialist.execute(valid_state)
    assert result["error_report"] is None

    # Test failure
    result = specialist.execute(invalid_state)
    assert result["error_report"] is not None
```

---

## Integration Test Checklist

When writing a new integration test, verify:

- [ ] Uses real config files (not mocks)
- [ ] Tests actual component interactions
- [ ] Validates both success and error paths
- [ ] Checks state transitions
- [ ] Verifies artifacts are created/consumed correctly
- [ ] Includes clear assertions with helpful error messages
- [ ] Runs in Docker environment (not local machine only)
- [ ] Cleans up any created resources (files, database entries)

---

## Related Documentation

- **Unit Testing**: See `CREATING_A_NEW_SPECIALIST.md` Step 4 for unit test examples
- **Test Architecture**: See `TEST_SUITE_SUMMARY.md` for overall test organization
- **ADRs**:
  - ADR-CORE-001: Fail-Fast Startup Validation
  - ADR-CORE-006: Fail-Fast on Unknown Graph Routes
  - ADR-CORE-CHAT-002: Tiered Chat Subgraph
  - ADR-TS-001: Testing Infrastructure Refactoring

---

## Next Steps

1. **Choose a feature** to add integration tests for (see priorities below)
2. **Create test file** in `app/tests/integration/`
3. **Write tests** following patterns in this guide
4. **Run tests** locally: `docker compose exec app python -m pytest app/tests/integration/your_test.py -v`
5. **Debug failures** using verbose output and logs
6. **Commit tests** with descriptive commit message

### High-Priority Areas Needing Tests

1. **MCP Service Integration** - Service registration and invocation (CRITICAL)
2. **Tiered Chat End-to-End** - Full CORE-CHAT-002 workflow validation
3. **Artifact Passing** - Cross-specialist artifact flows
4. **Startup Validation** - Fail-fast mechanisms work correctly

---

## Conclusion

Integration tests are your safety net against configuration errors, contract mismatches, and state pollution bugs that unit tests miss. Follow this guide to write comprehensive integration tests that validate real-world scenarios and catch issues before production.

Remember: **If it's not tested with real components, it's not truly validated.**
