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
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    build-essential \
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
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for security.
RUN useradd --create-home appuser

# --- NEW SECTION ---
# Add the local bin directory for the new user to the PATH.
# This ensures that executables installed by pip (like uvicorn) are found.
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Switch to the non-root user.
USER appuser

# Copy all project files into the working directory.
COPY --chown=appuser:appuser . .

# Conditionally create the execution mode lock file based on the build argument.
RUN if [ "$EXECUTION_MODE" = "unsupervised" ]; then \
    touch .unsupervised_execution.lock; \
    fi

# Now, install Python dependencies from pyproject.toml.
RUN pip install --no-cache-dir -e '.[dev]'

# Install Playwright browsers (required for GeminiWebUIAdapter)
# Use --with-deps flag to install browser dependencies
RUN python -m playwright install --with-deps chromium

# Make the startup script executable.
RUN chmod +x start.sh

# Expose the ports for the API and the UI.
EXPOSE 8000
EXPOSE 5003

# Set the default command to run when the container starts.
CMD ["/bin/bash", "/app/start.sh"]
