# Adding MCP Services (Automation)

> Extracted from MCP_GUIDE.md for developer reference.

**Problem:** Manually adding external MCP services requires editing multiple files, building Docker images, and updating configurations.

**Solution:** The `add_mcp_service.py` script automates the entire process.

## Quick Start

**List Available Services:**
```bash
python scripts/add_mcp_service.py --list
```

**Install a Service:**
```bash
# Simple service (no API key required)
python scripts/add_mcp_service.py --service fetch

# Service requiring API key
python scripts/add_mcp_service.py --service brave-search

# Install as required service (fail-fast if unavailable)
python scripts/add_mcp_service.py --service postgres --required

# Auto-restart application after installation
python scripts/add_mcp_service.py --service fetch --auto-restart
```

### 10.2 How It Works

**Automation Workflow:**

```
┌────────────────────────────────────────────────────────┐
│ 1. Read Service Definition from Registry              │
│    config/mcp_registry.yaml                            │
│    - Package name (@modelcontextprotocol/server-fetch) │
│    - Environment variables needed                      │
│    - Docker args and volumes                           │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 2. Generate Dockerfile from Template                  │
│    docker/templates/node-mcp.Dockerfile                │
│    - Generic template works for all Node.js servers   │
│    - Build arg: NPM_PACKAGE                            │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 3. Build Docker Image                                  │
│    docker build -t mcp/fetch ...                       │
│    - Installs npm package globally                     │
│    - Creates entrypoint for stdio transport            │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 4. Update config.yaml (Atomic)                         │
│    - Create backup: config.yaml.backup                 │
│    - Write to temp: config.yaml.tmp                    │
│    - Atomic rename: tmp → config.yaml                  │
│    - Rollback capability if error occurs               │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 5. Update .env.example                                 │
│    - Add required environment variables                │
│    - Create MCP section if missing                     │
│    - Users copy values to .env                         │
└────────────┬───────────────────────────────────────────┘
             ↓
┌────────────────────────────────────────────────────────┐
│ 6. Display Next Steps                                  │
│    - List required env vars to add                     │
│    - Show restart command                              │
│    - Document service availability                     │
└────────────────────────────────────────────────────────┘
```

### 10.3 Available Services (Curated Registry)

The script uses a curated registry of known-good MCP servers. Current services:

| Service | Package | API Key Required | Description |
|---------|---------|------------------|-------------|
| `brave-search` | `@modelcontextprotocol/server-brave-search` | Yes (BRAVE_API_KEY) | Web search using Brave Search API |
| `fetch` | `@modelcontextprotocol/server-fetch` | No | HTTP fetching for web content |
| `puppeteer` | `@modelcontextprotocol/server-puppeteer` | No | Browser automation and web scraping |
| `filesystem` | `@modelcontextprotocol/server-filesystem` | No | Secure file operations with directory boundaries |
| `postgres` | `@modelcontextprotocol/server-postgres` | Yes (POSTGRES_CONNECTION_STRING) | PostgreSQL database operations |
| `sqlite` | `@modelcontextprotocol/server-sqlite` | No | SQLite database operations |

**Registry Location:** `config/mcp_registry.yaml`

**Adding Custom Services:**

```yaml
# config/mcp_registry.yaml
available_servers:
  my-custom-service:
    source: "npm"
    package: "@org/server-name"
    dockerfile_template: "node-mcp"
    env_vars:
      - API_KEY
    args:
      - "--option=value"
    volumes:
      - "${WORKSPACE_PATH}/data:/data"
    description: "Custom service description"
    docs_url: "https://github.com/..."
```

### 10.4 Installation Example

**Installing Brave Search:**

```bash
$ python scripts/add_mcp_service.py --service brave-search

======================================================================
Installing MCP service: brave-search
======================================================================

Description: Web search using Brave Search API
Documentation: https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search

✓ Prerequisites validated
✓ Docker image 'mcp/brave-search' built successfully
✓ config.yaml updated with service 'brave-search'
  Backup saved to config.yaml.backup
✓ .env.example updated with environment variables

======================================================================
✓ Installation complete!
======================================================================

NEXT STEPS:
1. Add the following environment variables to your .env file:
   BRAVE_API_KEY=<your-api-key>

2. Restart the application:
   docker compose restart app

Service 'brave-search' is now available via external MCP!
Check config.yaml to verify configuration.
```

**Resulting Configuration:**

```yaml
# config.yaml (auto-generated)
mcp:
  external_mcp:
    enabled: true
    services:
      brave-search:
        enabled: true
        required: false
        command: "docker"
        args:
          - "run"
          - "-i"  # CRITICAL: maintains stdin for stdio transport
          - "--rm"
          - "-e"
          - "BRAVE_API_KEY=${BRAVE_API_KEY}"
          - "mcp/brave-search"
```

### 10.5 Language Independence

**Key Design Principle:** MCP + Docker abstracts language completely.

The same generic Dockerfile template works for:
- Node.js servers (via `npx`)
- Python servers (future: `python-mcp.Dockerfile`)
- Go binaries (future: `go-mcp.Dockerfile`)
- Pre-built containers (future: `prebuilt` template)

**Example Node.js Template:**

```dockerfile
# docker/templates/node-mcp.Dockerfile
ARG NPM_PACKAGE
FROM node:lts-alpine

# Install the MCP server package globally
RUN npm install -g ${NPM_PACKAGE}

# Create entrypoint that runs the MCP server
RUN echo '#!/bin/sh' > /usr/local/bin/mcp-server && \
    echo 'exec npx -y ${NPM_PACKAGE} "$@"' >> /usr/local/bin/mcp-server && \
    chmod +x /usr/local/bin/mcp-server

# MCP protocol uses stdin/stdout for JSON-RPC
ENTRYPOINT ["/usr/local/bin/mcp-server"]
CMD []
```

**Build Process:**

```bash
# Automatic build via script
docker build \
  --build-arg NPM_PACKAGE=@modelcontextprotocol/server-fetch \
  -f docker/templates/node-mcp.Dockerfile \
  -t mcp/fetch \
  .
```

### 10.6 Security & Validation

**Prerequisite Checks:**

1. **Docker Running:**
   ```bash
   docker ps  # Must succeed
   ```

2. **Template Exists:**
   ```bash
   ls docker/templates/node-mcp.Dockerfile  # Must exist
   ```

**Atomic Configuration Updates:**

```python
# Rollback-safe pattern (temp file + rename)
backup_path = config.yaml.backup
shutil.copy(config.yaml, backup_path)

temp_path = config.yaml.tmp
with open(temp_path, "w") as f:
    yaml.dump(config, f)

temp_path.replace(config.yaml)  # Atomic operation
```

**Failure Modes:**
- Docker build fails → No config changes made
- Config update fails → Backup available for rollback
- Template missing → Error before any changes

### 10.7 Offline/Fallback Resilience

**Progressive Resilience (MANDATE-CORE-001):**

The automation system supports offline operation:

1. **Local Docker Images:** Pre-built images work without internet
2. **Registry Caching:** `mcp_registry.yaml` cached locally
3. **Graceful Degradation:** Missing services don't break application
4. **Optional vs Required:** `required: false` allows partial availability

**Offline Workflow:**

```bash
# Pre-build images while online
python scripts/add_mcp_service.py --service fetch
python scripts/add_mcp_service.py --service sqlite

# Later, offline - images available from local Docker cache
docker compose up  # Works with pre-built images
```

### 10.8 Testing

**Unit Tests:** `app/tests/scripts/test_add_mcp_service.py`

```bash
# Run installer tests
python -m pytest app/tests/scripts/test_add_mcp_service.py -v

# Coverage includes:
# - Registry loading (2 tests)
# - Prerequisite validation (3 tests)
# - Docker image building (2 tests)
# - Config.yaml atomic updates (5 tests)
# - .env.example updates (3 tests)
# - Full installation workflow (5 tests)
# Total: 22 tests
```

**Test Coverage:**
- Registry loading and service info retrieval
- Prerequisite validation (Docker, templates)
- Docker image build success/failure
- Atomic config updates with rollback
- Environment variable updates
- Full installation workflow
- Error handling scenarios

### 10.9 Future Enhancements

**Potential Additions to Registry:**

- **Community Servers:**
  - Memory server (knowledge graph)
  - YouTube transcripts
  - Slack integration
  - DuckDuckGo search

- **Custom Templates:**
  - `python-mcp.Dockerfile` for Python servers
  - `go-mcp.Dockerfile` for Go binaries
  - `prebuilt.Dockerfile` for Docker Hub images

**Self-Service Addition:**

This automation enables **LAS self-modification** - the system could potentially add MCP services to itself based on user requests:

```
User: "I need PostgreSQL database access"
  ↓
Triage identifies need for postgres MCP service
  ↓
SystemsArchitect determines requirement
  ↓
ShellSpecialist executes: python scripts/add_mcp_service.py --service postgres
  ↓
System prompts user for POSTGRES_CONNECTION_STRING
  ↓
Application restarts with new capability
```

**Discovery vs Curated Registry:**

Current approach uses **curated registry** (known-good services). Future could support:
- Dynamic discovery from Docker Hub
- Community marketplace integration
- Security scanning before installation

---

