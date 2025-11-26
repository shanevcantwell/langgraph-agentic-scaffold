"""
Checkpoint Manager for HitL (Human-in-the-Loop) workflows.

ADR-CORE-018: Provides state persistence for interrupt/resume patterns.

Usage:
    checkpointer = get_checkpointer(user_settings)
    graph = workflow.compile(checkpointer=checkpointer)

Configuration (user_settings.yaml):
    checkpointing:
      enabled: true
      backend: "sqlite"  # or "postgres" for production
      sqlite_path: "./data/checkpoints.db"
      # postgres_url: "${DATABASE_URL}"  # for production
"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_checkpointer(config: dict) -> Optional[object]:
    """
    Initialize and return the appropriate checkpointer based on configuration.

    Args:
        config: User settings dictionary containing checkpointing configuration.

    Returns:
        A LangGraph checkpointer instance, or None if checkpointing is disabled.

    Raises:
        ImportError: If required checkpoint backend package is not installed.
        ValueError: If unknown backend is specified.
    """
    checkpoint_config = config.get("checkpointing", {})

    if not checkpoint_config.get("enabled", False):
        logger.info("Checkpointing is disabled in configuration")
        return None

    backend = checkpoint_config.get("backend", "sqlite")

    if backend == "sqlite":
        return _init_sqlite_checkpointer(checkpoint_config)
    elif backend == "postgres":
        return _init_postgres_checkpointer(checkpoint_config)
    else:
        raise ValueError(f"Unknown checkpointing backend: {backend}")


def _init_sqlite_checkpointer(config: dict):
    """
    Initialize SQLite-based checkpointer for local development.

    Low complexity, single-process. Good for dev/testing.
    Returns None with warning if package not installed (graceful degradation).
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite not installed. Checkpointing DISABLED. "
            "Install with: pip install langgraph-checkpoint-sqlite"
        )
        return None

    db_path = config.get("sqlite_path", "./data/checkpoints.db")

    # Ensure directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # SqliteSaver expects a connection string
    conn_string = f"sqlite:///{db_path}"

    logger.info(f"Initializing SQLite checkpointer at: {db_path}")
    return SqliteSaver.from_conn_string(conn_string)


def _init_postgres_checkpointer(config: dict):
    """
    Initialize PostgreSQL-based checkpointer for production.

    Supports multi-process access, pgvector for future Codex integration.
    Returns None with warning if package not installed (graceful degradation).
    """
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-postgres not installed. Checkpointing DISABLED. "
            "Install with: pip install langgraph-checkpoint-postgres"
        )
        return None

    postgres_url = config.get("postgres_url")

    if not postgres_url:
        raise ValueError(
            "postgres_url is required for PostgreSQL checkpointing. "
            "Set checkpointing.postgres_url in user_settings.yaml"
        )

    # Expand environment variables in URL (e.g., ${DATABASE_URL})
    if postgres_url.startswith("${") and postgres_url.endswith("}"):
        env_var = postgres_url[2:-1]
        postgres_url = os.environ.get(env_var)
        if not postgres_url:
            raise ValueError(f"Environment variable {env_var} is not set")

    logger.info("Initializing PostgreSQL checkpointer")
    return PostgresSaver.from_conn_string(postgres_url)
