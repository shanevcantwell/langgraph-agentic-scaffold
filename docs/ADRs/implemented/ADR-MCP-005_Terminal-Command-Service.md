# ADR-MCP-005: Terminal Command MCP Service

**Status:** Implemented (2026-02-18 audit). terminal-mcp container running in docker-compose.yml, sandboxed shell execution via MCP.
**Date:** 2026-01-26
**Related:** ADR-MCP-003 (External MCP Container Integration), ADR-CORE-035 (Filesystem Architecture)

---

## Context

Users issue shell commands like `pwd`, `ls -la`, `git status` expecting the system to execute them. Currently:

1. **Triage** interprets `pwd` as "list directory contents" and produces a `list_directory` action
2. **Router** routes to `batch_processor_specialist` (file operations)
3. **BatchProcessor** attempts `list_directory` MCP call which fails or returns wrong result

The system has no capability to execute arbitrary shell commands. The `filesystem` MCP only provides file operations (read, write, move, etc.), not command execution.

**Example failure trace** (archive `run_20260126_025004_99d6d89e.zip`):
```
User: pwd
→ Triage: list_directory on "."
→ Router: batch_processor_specialist
→ BatchProcessor: Permission Denied (list_directory not in allowed tools)
```

---

## Decision

Create a new **Terminal Command MCP Service** that:

1. Runs in a sandboxed Docker container (like `filesystem-mcp`)
2. Exposes shell command execution via MCP protocol
3. Uses allowlist-based command filtering for security
4. Returns stdout, stderr, and exit code

### Service Interface

```python
# MCP Tools exposed
tools:
  - run_command:
      description: "Execute a shell command and return results"
      parameters:
        command: str       # The command to execute
        timeout_ms: int    # Max execution time (default 30000)
        cwd: str           # Working directory (default /workspace)
      returns:
        stdout: str
        stderr: str
        exit_code: int

  - get_cwd:
      description: "Return current working directory path"
      returns:
        path: str

  - get_env:
      description: "Return environment variable value"
      parameters:
        name: str
      returns:
        value: str | null
```

### Security Model

**Tier 1 - Allowlist (Default)**
```yaml
terminal_mcp:
  security_mode: allowlist
  allowed_commands:
    - pwd
    - ls
    - cat
    - head
    - tail
    - wc
    - grep
    - find
    - echo
    - date
    - whoami
    - git status
    - git log
    - git diff
```

**Tier 2 - Pattern-Based**
```yaml
terminal_mcp:
  security_mode: pattern
  allowed_patterns:
    - "^ls( |$)"           # ls with any flags
    - "^git (status|log|diff|branch)"
    - "^cat [a-zA-Z0-9_./]+"
  blocked_patterns:
    - "rm -rf"
    - "sudo"
    - "> /dev"
    - "| bash"
```

**Tier 3 - Unrestricted (Dangerous)**
```yaml
terminal_mcp:
  security_mode: unrestricted  # NOT RECOMMENDED
```

---

## Implementation

### Docker Container

```dockerfile
# docker/terminal-mcp/Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY terminal_mcp_server.py .
COPY requirements.txt .
RUN pip install -r requirements.txt

# Run as non-root user
RUN useradd -m mcpuser
USER mcpuser

CMD ["python", "terminal_mcp_server.py"]
```

### Docker Compose Addition

```yaml
# docker-compose.yml
services:
  terminal-mcp:
    build:
      context: ./docker/terminal-mcp
    container_name: terminal-mcp
    volumes:
      - ./workspace:/workspace:rw
    environment:
      - SECURITY_MODE=allowlist
      - WORKSPACE_PATH=/workspace
    networks:
      - las-network
    restart: unless-stopped
```

### MCP Server Implementation

```python
# docker/terminal-mcp/terminal_mcp_server.py
import subprocess
import os
from mcp.server import Server
from mcp.types import Tool, TextContent

ALLOWED_COMMANDS = {"pwd", "ls", "cat", "head", "tail", "wc", "grep", "find", "echo", "date", "whoami"}

server = Server("terminal-mcp")

@server.tool()
async def run_command(command: str, timeout_ms: int = 30000, cwd: str = "/workspace") -> dict:
    """Execute a shell command with security filtering."""

    # Security check
    base_command = command.split()[0] if command.split() else ""
    if base_command not in ALLOWED_COMMANDS:
        return {
            "stdout": "",
            "stderr": f"Command '{base_command}' not in allowlist: {ALLOWED_COMMANDS}",
            "exit_code": 126
        }

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            cwd=cwd
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout_ms}ms",
            "exit_code": 124
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1
        }

@server.tool()
async def get_cwd() -> dict:
    """Return current working directory."""
    return {"path": os.getcwd()}

@server.tool()
async def get_env(name: str) -> dict:
    """Return environment variable value."""
    return {"value": os.environ.get(name)}
```

### Config Integration

```yaml
# config.yaml
mcp:
  external:
    terminal:
      container: "terminal-mcp"
      transport: "stdio"

specialists:
  # Grant terminal access to specific specialists
  chat_specialist:
    tools:
      terminal:
        - run_command
        - get_cwd

  batch_processor_specialist:
    tools:
      terminal:
        - run_command
        - get_cwd
```

---

## Routing Integration

### Triage Updates

Add `terminal_command` as a context action type:

```python
# context_schema.py
class ContextActionType(str, Enum):
    RESEARCH = "research"
    READ_FILE = "read_file"
    LIST_DIRECTORY = "list_directory"
    SUMMARIZE = "summarize"
    ASK_USER = "ask_user"
    TERMINAL_COMMAND = "terminal_command"  # NEW
```

### Triage Prompt Updates

```markdown
## Context Actions

| Action | Purpose | Target |
|--------|---------|--------|
| `terminal_command` | Execute shell command | Command string |
| `read_file` | Read a workspace file | File path |
...

## Examples

```json
{"reasoning": "User wants current directory path", "actions": [{"type": "terminal_command", "target": "pwd", "description": "Get working directory"}], "recommended_specialists": ["chat_specialist"]}
```
```

---

## Consequences

### Positive

1. **Enables shell command execution** - System can now handle `pwd`, `ls`, `git status`, etc.
2. **Sandboxed execution** - Commands run in isolated container with limited privileges
3. **Allowlist security** - Only pre-approved commands can execute
4. **Consistent MCP pattern** - Follows existing external MCP architecture

### Negative

1. **Security surface area** - Any command execution is a potential risk
2. **Another container** - Adds to docker-compose complexity
3. **Allowlist maintenance** - Need to update allowlist as needs evolve

### Mitigations

- Default to most restrictive allowlist
- Run container as non-root user
- No network access from terminal container
- Audit logging of all executed commands
- Timeout protection against runaway commands

---

## Alternatives Considered

### Alternative 1: Execute in Main Container (Rejected)

Run commands directly in `langgraph-app` container.

**Rejected because:**
- Increases attack surface of main application
- No isolation between LLM-driven commands and app code
- Harder to audit/restrict

### Alternative 2: Map Commands to File Operations (Current Workaround)

Translate `pwd` → `list_directory(".")`, etc.

**Rejected because:**
- Semantic mismatch (pwd ≠ list directory)
- Can't handle `git`, `grep`, `find`, etc.
- User expectation mismatch

### Alternative 3: Host Machine Execution (Rejected)

Execute commands on the Docker host.

**Rejected because:**
- Extreme security risk
- Breaks container isolation model
- No sandboxing possible

---

## Implementation Checklist

1. [ ] Create `docker/terminal-mcp/` directory structure
2. [ ] Implement `terminal_mcp_server.py` with allowlist security
3. [ ] Add `terminal-mcp` service to `docker-compose.yml`
4. [ ] Update `ExternalMcpClient` to connect to terminal-mcp
5. [ ] Add `TERMINAL_COMMAND` to `ContextActionType` enum
6. [ ] Update Triage prompt with `terminal_command` action type
7. [ ] Update Facilitator to handle `terminal_command` actions
8. [ ] Add `terminal` tool permissions to relevant specialists in config.yaml
9. [ ] Write integration tests for terminal command execution
10. [ ] Document security model in CONFIGURATION_GUIDE.md

---

## References

- ADR-MCP-003: External MCP Container Integration
- ADR-CORE-035: Filesystem Architecture Consolidation
- Issue #64: Triage routing failure for shell commands
- Issue #65: BatchProcessor permission mismatch
