# app/src/utils/environment.py
"""
Environment detection utilities for smart runtime behavior.

Provides detection for Docker vs host execution to enable:
- Informative test skipping (not silent)
- Clear diagnostics in verify_connectivity.py
- Guidance for users running outside expected environment
"""
import os


def is_docker() -> bool:
    """
    Detect if running inside a Docker container.

    Checks:
    - /.dockerenv file (created by Docker)
    - DOCKER_CONTAINER env var (explicit signal)
    """
    return os.path.exists("/.dockerenv") or bool(os.environ.get("DOCKER_CONTAINER"))


def get_environment_context() -> dict:
    """
    Return environment context for diagnostics.

    Useful for health checks and debugging.
    """
    return {
        "is_docker": is_docker(),
        "has_local_inference_url": bool(os.environ.get("LOCAL_INFERENCE_BASE_URL") or os.environ.get("LMSTUDIO_BASE_URL")),
        "has_gemini_key": bool(os.environ.get("GOOGLE_API_KEY")),
        "langchain_tracing": os.environ.get("LANGCHAIN_TRACING_V2") == "true",
    }
