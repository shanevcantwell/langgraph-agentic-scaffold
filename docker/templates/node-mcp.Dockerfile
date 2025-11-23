# Generic Dockerfile template for Node.js-based MCP servers
# This template is used by add_mcp_service.py script to build MCP server images
#
# Build args:
# - NPM_PACKAGE: The npm package to install (e.g., @modelcontextprotocol/server-brave-search)
#
# Usage:
#   docker build \
#     --build-arg NPM_PACKAGE="@modelcontextprotocol/server-fetch" \
#     -f docker/templates/node-mcp.Dockerfile \
#     -t mcp/fetch \
#     .

ARG NPM_PACKAGE
FROM node:lts-alpine

# Install the MCP server package globally
RUN npm install -g ${NPM_PACKAGE}

# Create a simple entrypoint script that runs the MCP server
# MCP servers use stdio for JSON-RPC communication
RUN echo '#!/bin/sh' > /usr/local/bin/mcp-server && \
    echo 'exec npx -y ${NPM_PACKAGE} "$@"' >> /usr/local/bin/mcp-server && \
    chmod +x /usr/local/bin/mcp-server

# MCP protocol uses stdin/stdout for JSON-RPC
# Container must be run with -i (interactive) flag to maintain stdin
ENTRYPOINT ["/usr/local/bin/mcp-server"]

# Default CMD can be overridden by docker run args
CMD []
