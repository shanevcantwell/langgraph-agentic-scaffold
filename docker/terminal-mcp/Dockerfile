# Terminal MCP Server - Sandboxed shell command execution
# Implements ADR-MCP-005: Terminal Command MCP Service
#
# Security:
# - Runs as non-root user
# - Allowlist-based command filtering
# - No network access (add --network none when running)
# - Limited to /workspace volume

FROM python:3.11-slim

# Install common shell utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    findutils \
    coreutils \
    grep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy server code
COPY terminal_mcp_server.py .

# Create non-root user for security
RUN useradd -m -s /bin/bash mcpuser && \
    mkdir -p /workspace && \
    chown mcpuser:mcpuser /workspace

# Switch to non-root user
USER mcpuser

# Default environment
ENV SECURITY_MODE=allowlist
ENV WORKSPACE_PATH=/workspace

# MCP uses stdio for JSON-RPC - container must be run with -i flag
CMD ["python", "-u", "terminal_mcp_server.py"]
