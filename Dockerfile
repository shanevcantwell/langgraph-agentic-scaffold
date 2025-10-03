# /Dockerfile

# Start from a standard Python base image.
FROM python:3.12-slim

# Set the working directory inside the container.
WORKDIR /app

# Declare a build-time argument for the execution mode. Defaults to 'supervised'.
# Can be overridden during build with --build-arg EXECUTION_MODE=unsupervised
ARG EXECUTION_MODE=supervised

# Install system dependencies. 'build-essential' includes kernel headers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    build-essential && \
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

# Make the startup script executable.
RUN chmod +x start.sh

# Expose the ports for the API and the UI.
EXPOSE 8000
EXPOSE 5003

# Set the default command to run when the container starts.
CMD ["/bin/bash", "/app/start.sh"]