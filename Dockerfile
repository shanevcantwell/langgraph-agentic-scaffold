# /Dockerfile

# Start from a standard Python base image.
FROM python:3.12-slim

# Set the working directory inside the container.
WORKDIR /app

# Ensure the logs folder is present
RUN mkdir -p logs

# Declare a build-time argument for the execution mode. Defaults to 'supervised'.
# Can be overridden during build with --build-arg EXECUTION_MODE=unsupervised
ARG EXECUTION_MODE=supervised

# Install system dependencies. 'build-essential' includes kernel headers.
# Playwright dependencies: https://playwright.dev/docs/ci#docker
# Docker CLI for external MCP container spawning (ADR-MCP-003)
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    build-essential \
    curl \
    ca-certificates \
    # Playwright browser dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 && \
    # Install Docker CLI (for spawning external MCP containers)
    curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar xz --strip-components=1 -C /usr/local/bin docker/docker && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for security.
RUN useradd --create-home appuser

# --- NEW SECTION ---
# Add the local bin directory for the new user to the PATH.
# This ensures that executables installed by pip (like uvicorn) are found.
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Copy all project files into the working directory (as root, then chown).
COPY --chown=appuser:appuser . .

# Install Python dependencies as root (needed for Playwright system deps)
RUN pip install --no-cache-dir -e '.[dev]'

# Install Playwright browsers with system dependencies (must be run as root)
# This installs Chromium and its system-level dependencies
RUN python -m playwright install --with-deps chromium

# NOW switch to the non-root user for runtime.
USER appuser

# Conditionally create the execution mode lock file based on the build argument.
RUN if [ "$EXECUTION_MODE" = "unsupervised" ]; then \
    touch .unsupervised_execution.lock; \
    fi

# Make the startup script executable.
RUN chmod +x start.sh

# Expose the ports for the API and the UI.
EXPOSE 8000
EXPOSE 5003

# Set the default command to run when the container starts.
CMD ["/bin/bash", "/app/start.sh"]
