# ADR-CORE-027: Navigation-MCP Integration

**Status:** IMPLEMENTED
**Date:** 2025-12-18
**Implements:** External MCP Integration for Navigation Services
**Related ADRs:** ADR-CORE-008 (MCP Architecture), ADR-PLATFORM-001 (Unified Container Architecture)

---

## Context

The system needed capabilities beyond what FileSpecialist provides via internal MCP:

1. **Recursive directory deletion** - FileSpecialist can only delete individual files
2. **Glob pattern file search** - No pattern-based file discovery
3. **Web browser automation** - No capability for web navigation
4. **Visual grounding** - No ability to interact with web elements via natural language

These capabilities require **external services** running in separate containers with specialized dependencies (Playwright, browser runtimes, visual AI models). Internal MCP (ADR-CORE-008) is designed for synchronous, in-process service calls - it cannot orchestrate external containerized services.

### Key Challenge: Pre-flight Check Timing

During implementation, we discovered a timing issue with specialist loading:

```
GraphBuilder.build()
    -> load_and_configure_specialists()
        -> specialist._perform_pre_flight_checks()  # external_mcp_client is None!
    -> ...
    -> initialize_external_mcp()  # Client injected AFTER pre-flight checks
```

Specialists that require `external_mcp_client` would fail pre-flight checks and be disabled before the client was injected.

---

## Decision

We introduce **Navigation-MCP** as an external container service providing tree traversal and browser automation, with a two-layer specialist architecture that handles async client injection gracefully.

### Phase 1: Container Architecture

**New container: `navigator`**

```yaml
# docker-compose.yml
services:
  navigator:
    build: ./navigation-mcp
    profiles: ["navigator"]  # Optional service
    volumes:
      - ./workspace:/workspace:rw
    networks:
      - app-network
    environment:
      - FARA_ENDPOINT=http://proxy:8080/fara  # Visual grounding model
```

**Profile-based activation:**
- Navigator is optional (not all deployments need browser automation)
- Activated via: `docker-compose --profile navigator up -d`
- Graceful degradation when unavailable

### Phase 2: NavigatorSpecialist (Filesystem Operations)

```python
class NavigatorSpecialist(BaseSpecialist):
    """
    Specialist for complex filesystem operations requiring tree traversal.

    Capabilities:
    - Recursive directory deletion
    - Glob pattern file search
    - Tree navigation with history
    """

    SERVICE_NAME = "navigator"
    DRIVER_FS = "fs"

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.external_mcp_client = None  # Injected by GraphBuilder
```

**Session-based operations:**
```python
def delete_recursive(self, session_id: str, path: str) -> Dict[str, Any]:
    return self._call_navigator("delete", session_id, target=path, recursive=True)

def find_files(self, session_id: str, pattern: str, path: str = ".") -> Dict[str, Any]:
    self._call_navigator("goto", session_id, location=path)
    return self._call_navigator("find", session_id, pattern=pattern)
```

### Phase 3: NavigatorBrowserSpecialist (Web Navigation)

```python
class NavigatorBrowserSpecialist(BaseSpecialist):
    """
    Specialist for web navigation with visual grounding.

    Uses Fara visual AI model for natural language element interaction:
    - "Click the Submit button"
    - "Type 'hello' in the search box"
    """

    def navigate_to(self, session_id: str, url: str) -> Dict[str, Any]:
        return sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "goto",
            {"session_id": session_id, "driver": "web", "location": url}
        )

    def click_element(self, session_id: str, element_description: str) -> Dict[str, Any]:
        # Visual grounding: "the blue login button" -> coordinates
        return sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "click",
            {"session_id": session_id, "driver": "web", "target": element_description}
        )
```

### Phase 4: Browser Session Persistence

Multi-turn conversations require session persistence:

```python
BROWSER_SESSION_ARTIFACT_KEY = "browser_session"

def _get_or_create_session(self, state: Dict[str, Any], persist: bool = True) -> Optional[str]:
    if persist:
        existing = self._get_existing_session(state)
        if existing and self._validate_session(existing):
            logger.info(f"Reusing existing browser session: {existing}")
            return existing
    return self._create_browser_session()

def _merge_result_with_session(self, result: Dict[str, Any], session_id: str, persist: bool) -> Dict[str, Any]:
    if persist:
        artifacts = result.get("artifacts", {})
        artifacts[self.BROWSER_SESSION_ARTIFACT_KEY] = {"session_id": session_id, "persist": True}
        result["artifacts"] = artifacts
    return result
```

### Pre-flight Check Pattern (Critical Fix)

**Problem:** `external_mcp_client` is injected AFTER `_perform_pre_flight_checks()` runs.

**Solution:** Two-stage validation pattern:

```python
def _perform_pre_flight_checks(self) -> bool:
    """
    At load time: Return True to allow loading (client not injected yet)
    At runtime: Verify service is connected
    """
    # Load time: client not injected - allow loading
    if not self.external_mcp_client:
        return True

    # Runtime: verify connection
    if not self.external_mcp_client.is_connected(self.SERVICE_NAME):
        logger.warning(f"{self.specialist_name}: navigator service not connected")
        return False
    return True

def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
    # Runtime check: client must be injected
    if not self.external_mcp_client:
        return self._handle_navigator_unavailable(state)

    # Runtime check: service must be connected
    if not self._perform_pre_flight_checks():
        return self._handle_navigator_unavailable(state)

    # ... proceed with operation
```

**Key insight:** Pre-flight checks serve dual purposes:
1. **Load-time:** Determine if specialist can be added to graph (always allow for external MCP)
2. **Runtime:** Graceful degradation when service unavailable

---

## Graceful Degradation

When navigator service is unavailable:

```python
def _handle_navigator_unavailable(self, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "messages": [AIMessage(
            content="The Navigator service is currently unavailable. "
                    "For simple file operations (read, write, delete single files), "
                    "you can use the File Operations specialist instead.\n\n"
                    "Navigator is needed for:\n"
                    "- Recursive directory deletion\n"
                    "- Glob pattern file search\n"
                    "- Tree traversal operations"
        )]
    }
```

---

## Internal MCP Registration

Both specialists register as internal MCP services for other specialists:

```python
def register_mcp_services(self, registry):
    registry.register_service(self.specialist_name, {
        "delete_recursive": self._mcp_delete_recursive,
        "find_files": self._mcp_find_files,
        "list_directory": self._mcp_list_directory,
        "is_available": self._mcp_is_available,
    })
```

This enables patterns like:
```python
# From another specialist
if self.mcp_client.call("navigator_specialist", "is_available"):
    results = self.mcp_client.call("navigator_specialist", "find_files", pattern="*.py")
```

---

## Consequences

### Positive

1. **Extended capabilities** - Recursive delete, glob search, browser automation
2. **Visual grounding** - Natural language element interaction via Fara
3. **Graceful degradation** - System works without navigator service
4. **Session persistence** - Multi-turn browser conversations
5. **Container isolation** - Browser dependencies isolated from main app
6. **Profile-based activation** - Optional service doesn't impact base deployments

### Negative

1. **External dependency** - Navigator container must be running for full functionality
2. **Latency overhead** - Cross-container MCP calls vs in-process
3. **Complexity** - Two-stage pre-flight pattern requires careful implementation
4. **Resource usage** - Browser sessions consume memory

### Risks & Mitigations

**Risk:** Session leaks if browser sessions not properly destroyed
**Mitigation:** Session timeout (1 hour), explicit cleanup_session() method

**Risk:** Visual grounding fails on complex UIs
**Mitigation:** Fallback to standard element interaction, clear error messages

**Risk:** Container startup delays
**Mitigation:** Graceful degradation, connection retry logic

---

## Implementation Phases

| Phase | Commit | Description |
|-------|--------|-------------|
| 1 | 15faf16 | Navigation-MCP container integration |
| 2 | 2807519 | NavigatorSpecialist for filesystem operations |
| 3 | 98ed3c8 | NavigatorBrowserSpecialist for web navigation |
| 4 | 6d8016d | Browser session persistence |
| Fix | 3112755 | Pre-flight check timing fix |

---

## References

- [navigation-mcp](workspace/design-docs/navigator-mcp/) - Container generation plan
- [app/src/specialists/navigator_specialist.py](app/src/specialists/navigator_specialist.py)
- [app/src/specialists/navigator_browser_specialist.py](app/src/specialists/navigator_browser_specialist.py)
- Test suites: 146 tests across unit and integration
