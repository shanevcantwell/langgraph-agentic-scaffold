# LAS v1.0 Release Preparation

> Pre-LAP release to establish clean baseline on GitHub.

---

## Release Scope: "Bedrock Complete"

**Version:** 0.1.0
**Tagline:** Multi-model agentic orchestration with structural safety

### Included
- All Bedrock workstreams (37/37 complete)
- Tiered Chat, Context Engineering, Hybrid Routing
- MCP infrastructure (internal + external)
- V.E.G.A.S. Terminal UI
- ReActMixin, Deep Research pipeline
- surf-mcp browser integration

### Excluded (LAP scope)
- Deep Agent Lifecycle (ADR-CORE-038)
- Model Registry MCP (ADR-CORE-039)
- WebUI LLM Adapters (ADR-CORE-033)

---

## Pre-Release Checklist

### 1. Documentation

| Task | Status | Notes |
|------|--------|-------|
| LAS_v1_REFERENCE.md | ✅ | Authoritative architecture reference |
| FLOWS.md | ✅ | Prompt → specialist flows with Mermaid diagrams |
| API_REFERENCE.md | ✅ | REST API documentation |
| MCP_GUIDE.md | ✅ | Rewritten (155 lines, was 1600+) |
| CONFIGURATION_GUIDE.md | ✅ | 3-tier config system |
| README.md | ✅ | Roadmap 100%, test counts updated |
| docs/dev/ structure | ✅ | TESTING, SPECIALISTS, SUBGRAPHS, MCP_AUTOMATION |
| docs/generated/ | ✅ | TEST_SUITE_SUMMARY, PROJECT_STRUCTURE |

**Current docs/ structure:**
```
docs/
├── LAS_v1_REFERENCE.md    # Architecture reference for LAP planning
├── FLOWS.md               # Prompt → specialist flows (Mermaid diagrams)
├── API_REFERENCE.md       # REST API documentation
├── MCP_GUIDE.md           # MCP usage guide (concise)
├── CONFIGURATION_GUIDE.md # 3-tier config system
├── RELEASE_PREP.md        # This file
├── GRAPH_VISUALIZATIONS.md # Legacy diagrams (superseded by FLOWS.md)
├── dev/                   # Developer reference
│   ├── TESTING.md
│   ├── SPECIALISTS.md
│   ├── SUBGRAPHS.md
│   └── MCP_AUTOMATION.md
├── generated/             # Auto-generated
│   ├── TEST_SUITE_SUMMARY.md
│   └── PROJECT_STRUCTURE.md
├── archive/               # Superseded docs
└── ADRs -> symlink
```

### 2. Test Suite

| Task | Status | Notes |
|------|--------|-------|
| Flow integration tests | ✅ | test_flows.py - zero-mock API tests |
| Run full suite in Docker | ⬜ | `docker compose run --rm app pytest` |
| Fix failures | ⬜ | |
| Verify test count (~1000) | ⬜ | |

**New test file:** `app/tests/integration/test_flows.py`
- 13 flow tests matching FLOWS.md
- 5 invariant tests
- 2 execution order tests
- Browser tests skipped (require surf-mcp)

### 3. Code Cleanup

| Task | Status | Notes |
|------|--------|-------|
| NavigatorSpecialist fs driver | ⬜ | Mark deprecated, add TODO |
| FileSpecialist status | ⬜ | Still active per ADR-CORE-035 |
| Unused imports | ⬜ | Run linter |
| Type hints | ⬜ | Spot check critical files |

### 4. Configuration

| Task | Status | Notes |
|------|--------|-------|
| .env.example | ✅ | Placeholder values |
| config.yaml.example | ⬜ | Verify matches actual |
| user_settings.yaml.example | ⬜ | Verify matches actual |

### 5. Repository Hygiene

| Task | Status | Notes |
|------|--------|-------|
| .gitignore | ✅ | .env, credentials, etc. |
| No secrets in history | ⬜ | Verify |
| LICENSE | ✅ | MIT |
| CONTRIBUTING.md | ⬜ | Consider adding |

---

## Release Process

```bash
# 1. Ensure clean working directory
git status

# 2. Run full test suite
docker compose run --rm app pytest

# 3. Run flow tests specifically
docker compose run --rm app pytest app/tests/integration/test_flows.py -v

# 4. Update version (if applicable)
# pyproject.toml version field

# 5. Final commit
git add -A
git commit -m "Release preparation for v0.1.0"

# 6. Tag release
git tag -a v0.1.0 -m "LAS v0.1.0 - Bedrock Complete"

# 7. Push
git push origin development/testing
git push origin v0.1.0

# 8. Create GitHub release
gh release create v0.1.0 --title "v0.1.0 - Bedrock Complete" --notes-file RELEASE_NOTES.md
```

---

## Post-Release

1. **Archive** this prep doc
2. **Begin LAP** planning in separate repo
3. **GRAPH_VISUALIZATIONS.md** can be deleted (superseded by FLOWS.md)

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| FLOWS.md with Mermaid | Visual + text representation of all flows |
| API_REFERENCE.md | Needed for flow tests documentation |
| Zero-mock flow tests | Tests document actual system behavior |
| Keep GRAPH_VISUALIZATIONS.md | Legacy, but FLOWS.md now supersedes |
