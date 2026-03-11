# ADR-CORE-035: Filesystem Architecture Consolidation

**Status:** IMPLEMENTED
**Date:** 2025-12-20
**Implemented:** 2026-01-15
**Supersedes:** Parts of ADR-CORE-027 (Navigation-MCP fs driver)
**Category:** Architecture / MCP Infrastructure

---

## Context

LAS currently has **three overlapping filesystem implementations**:

| Component | Type | Location | Lines |
|-----------|------|----------|-------|
| `FileSpecialist` | Internal MCP service | `app/src/specialists/file_specialist.py` | 459 |
| `FileOperationsSpecialist` | User interface layer | `app/src/specialists/file_operations_specialist.py` | 233 |
| navigation-mcp `fs` driver | External MCP | `../navigation-mcp` | ~300 |

Additionally, `ManifestManager` handles project manifest operations separately.

This redundancy creates:
1. **Confusion** about which path to use
2. **Maintenance burden** across three implementations
3. **Inconsistent behavior** between internal and external MCP
4. **Scope creep** in navigation-mcp (bundling unrelated concerns)

---

## Decision

### 1. Adopt Official MCP Filesystem Server

Replace custom filesystem implementations with `@modelcontextprotocol/server-filesystem`:

```yaml
# docker-compose.yml
filesystem:
  image: mcp/filesystem  # or build from source
  volumes:
    - ./workspace:/workspace
  # Standard MCP stdio transport
```

**Rationale:**
- Maintained by Anthropic (not us)
- Richer feature set (batch reads, edit with diff, directory trees)
- MCP protocol compliant
- Implementation language (Node.js) is irrelevant - it's a containerized service

### 2. Strip Filesystem from navigation-mcp

navigation-mcp becomes **browser-only**:

```
navigation-mcp (v2 - focused)
├── Browser automation (goto, click, type, scroll)
├── Visual grounding (Fara integration)
├── Session management (cookies, tabs)
└── Online interaction ONLY
```

**Rationale - Online vs Offline distinction:**

| Aspect | Browser (Online) | Filesystem (Offline) |
|--------|------------------|----------------------|
| Nature | Read/interact with external state | Write/own persistent local state |
| Agency | Transient - you request, they persist | Persistent - you own the changes |
| Failure mode | Auth expired, UI changed | Disk full, permissions |
| Session | Stateful (cookies, DOM) | Stateless (paths) |

Bundling them created false equivalence. "Navigation" as tree traversal was conceptually clean but practically confusing.

### 3. Deprecate FileSpecialist and FileOperationsSpecialist

| Component | Action | Replacement |
|-----------|--------|-------------|
| `FileSpecialist` | DELETE | Official MCP filesystem server |
| `FileOperationsSpecialist` | DELETE | Direct MCP calls to filesystem server |
| `ManifestManager` | KEEP | LAS-specific business logic (schema validation) |

### 4. Future: Sandboxed Code Execution (Not This ADR)

Operations like `create_zip` are symptoms of a larger need: **execute arbitrary code in a sandbox**.

Rather than adding specialized operations (`create_zip`, `resize_image`, `parse_pdf`), the architectural direction is:

```
Future: Sandboxed Execution Service
├── Send code + context to container
├── Execute in isolation
├── Return results
└── Examples: compression, image processing, data transformation
```

This is **out of scope** for this ADR but noted as the strategic direction. Do not add more specialized file operations to compensate for removing `create_zip`.

---

## Implementation

### Phase 1: Add Official MCP Filesystem Server

1. Add `@modelcontextprotocol/server-filesystem` to docker-compose
2. Configure workspace mount and access controls
3. Update MCP client to route filesystem calls to new server
4. Add integration tests

### Phase 2: Migrate Callers

1. Identify all `mcp_client.call("file_specialist", ...)` usages
2. Update to call official filesystem server tools
3. Map operations:

| FileSpecialist | Official MCP FS |
|----------------|-----------------|
| `read_file` | `read_text_file` / `read_media_file` |
| `write_file` | `write_file` |
| `list_files` | `list_directory` |
| `create_directory` | `create_directory` |
| `delete_file` | (verify available) |
| `rename_file` | `move_file` |
| `append_to_file` | `edit_file` or write full content |
| `file_exists` | `get_file_info` (check for error) |

### Phase 3: Remove Deprecated Code

1. Delete `file_specialist.py`
2. Delete `file_operations_specialist.py`
3. Remove from `config.yaml`
4. Update router to not route to deleted specialists
5. Remove related tests (or migrate to test official server integration)

### Phase 4: Strip navigation-mcp

1. Remove `fs` driver from navigation-mcp
2. Remove workspace volume mount from navigator container
3. Remove `NAVIGATOR_FS_SANDBOX` config
4. Update navigation-mcp README
5. Update LAS's `test_navigator_mcp.py` to remove filesystem tests

---

## Consequences

### Positive

- **Single source of truth** for filesystem operations
- **Reduced maintenance** - Anthropic maintains the filesystem server
- **Cleaner navigation-mcp** - focused on browser automation
- **Conceptual clarity** - online (browser) vs offline (filesystem) separation
- **Richer features** - batch reads, directory trees, edit with diff

### Negative

- **Container overhead** - filesystem operations now require IPC
- **Latency increase** - sub-ms → ~10-50ms per operation
- **Migration effort** - update all callers

### Neutral

- `create_zip` capability removed (intentionally - see sandboxed execution note)
- `create_manifest` stays in ManifestManager (already separate)

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Official server missing features | Verify feature parity before migration |
| Latency impact on hot paths | Profile; ManifestManager stays internal if needed |
| Breaking changes in official server | Pin version; containerized = isolated |

---

## Files Affected

### Delete
- `app/src/specialists/file_specialist.py`
- `app/src/specialists/file_operations_specialist.py`
- `app/tests/specialists/test_file_operations_specialist.py`
- `app/tests/unit/test_file_specialist.py`
- `app/prompts/file_operations_prompt.md`
- `app/prompts/file_specialist_prompt.md`

### Modify
- `docker-compose.yml` - add filesystem server, remove navigator workspace mount
- `config.yaml` - remove file specialists
- `app/src/services/mcp_registry.py` - register filesystem server
- `docs/MCP_GUIDE.md` - update architecture docs
- `../navigation-mcp/` - remove fs driver (separate repo)

### Keep (No Changes)
- `app/src/utils/manifest_manager.py` - LAS-specific, stays internal

---

## References

- [Official MCP Filesystem Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- ADR-CORE-027: Navigation-MCP Integration (partially superseded)
- [NAVIGATION_MCP_CONSUMER_REPORT.md](../../../langgraph-agentic-scaffold/docs/reports/NAVIGATION_MCP_CONSUMER_REPORT.md)

---

## Implementation Notes

**2026-01-15 - Implementation Complete**

Phase 1-3 completed:
- Official `@modelcontextprotocol/server-filesystem` container added to docker-compose.yml
- `ExternalMcpClient` routes filesystem calls to containerized service
- Integration tests added: `app/tests/integration/test_filesystem_mcp.py`
- Callers migrated:
  - `FacilitatorSpecialist` uses filesystem MCP via `sync_call_external_mcp`
  - `BatchProcessorSpecialist` uses dispatcher pattern with filesystem MCP
- Deprecated code deleted:
  - `file_specialist.py`
  - `file_operations_specialist.py`
  - `test_file_specialist.py`
  - `test_file_operations_specialist.py`
  - `file_specialist_prompt.md`
  - `file_operations_prompt.md`
- `config.yaml` updated: `file_specialist` removed, `text_analysis_specialist.artifact_providers` updated
- `specialist_categories.py` updated: `SERVICE_LAYER` no longer references `file_specialist`

Phase 4 (navigation-mcp stripping) deferred - tracked separately.

---

## Decision Record

| Date | Decision | Author |
|------|----------|--------|
| 2025-12-20 | Proposed | Claude + Shane |
| 2026-01-15 | Implemented (Phase 1-3) | Claude + Shane |
