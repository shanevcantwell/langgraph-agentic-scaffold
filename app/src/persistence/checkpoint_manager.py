"""
Checkpoint Manager for workflow state persistence.

ARCHITECTURAL PATTERNS:

    1. ADR-CORE-042 HitL (Raise Hand / interrupt-resume):
       - MemorySaver (in-memory) enabled by default
       - Supports interrupt() / resume() for clarification flows
       - No database setup required
       - Use: get_default_checkpointer()

    2. RECESS/ESM "Subgraph as a Service":
       - Stateless API: client disconnects between turns
       - State must survive across HTTP request boundaries
       - REQUIRES external persistence (PostgreSQL/Redis/SQLite)
       - Use: create_checkpointer_context(config)

Default Usage (recommended for most workflows):
    from .persistence.checkpoint_manager import get_default_checkpointer
    checkpointer = get_default_checkpointer()
    workflow_runner.set_async_checkpointer(checkpointer)

Advanced Usage (RECESS/ESM with external persistence):
    async with create_checkpointer_context(config) as checkpointer:
        graph = workflow.compile(checkpointer=checkpointer)
        yield  # app runs
        # checkpointer automatically cleaned up

Configuration (user_settings.yaml) - only for external persistence:
    checkpointing:
      enabled: true
      backend: "sqlite"  # or "postgres" for production
      sqlite_path: "./data/checkpoints.db"
      # postgres_url: "${DATABASE_URL}"  # for production
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, AsyncIterator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_checkpointer_context(config: dict) -> AsyncIterator[Optional[object]]:
    """
    Create a checkpointer as an async context manager.

    This handles the lifecycle of async checkpointers (like AsyncSqliteSaver)
    which require async setup/teardown.

    Usage:
        async with create_checkpointer_context(config) as checkpointer:
            graph = workflow.compile(checkpointer=checkpointer)
            # use graph...
        # checkpointer automatically cleaned up

    Args:
        config: User settings dictionary containing checkpointing configuration.

    Yields:
        A LangGraph checkpointer instance, or None if checkpointing is disabled.
    """
    checkpoint_config = config.get("checkpointing", {})

    if not checkpoint_config.get("enabled", False):
        logger.info("Checkpointing is disabled in configuration")
        yield None
        return

    backend = checkpoint_config.get("backend", "sqlite")

    if backend == "sqlite":
        async with _create_sqlite_context(checkpoint_config) as checkpointer:
            yield checkpointer
    elif backend == "postgres":
        async with _create_postgres_context(checkpoint_config) as checkpointer:
            yield checkpointer
    else:
        raise ValueError(f"Unknown checkpointing backend: {backend}")


@asynccontextmanager
async def _create_sqlite_context(config: dict) -> AsyncIterator[Optional[object]]:
    """
    Create AsyncSqliteSaver as an async context manager.

    AsyncSqliteSaver requires async initialization because aiosqlite connections
    are async. The sync SqliteSaver doesn't support LangGraph's async streaming
    methods (astream, ainvoke).
    """
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite not installed. Checkpointing DISABLED. "
            "Install with: pip install langgraph-checkpoint-sqlite"
        )
        yield None
        return

    db_path = config.get("sqlite_path", "./data/checkpoints.db")

    # Ensure directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing AsyncSqliteSaver at: {db_path}")

    # AsyncSqliteSaver.from_conn_string is an async context manager
    # that yields the properly initialized saver
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        logger.info("AsyncSqliteSaver initialized successfully")
        yield saver

    logger.info("AsyncSqliteSaver connection closed")


@asynccontextmanager
async def _create_postgres_context(config: dict) -> AsyncIterator[Optional[object]]:
    """
    Create PostgresSaver as an async context manager.

    PostgreSQL supports async natively and handles concurrent access well.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-postgres not installed. Checkpointing DISABLED. "
            "Install with: pip install langgraph-checkpoint-postgres"
        )
        yield None
        return

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

    logger.info("Initializing AsyncPostgresSaver")

    async with AsyncPostgresSaver.from_conn_string(postgres_url) as saver:
        # Setup tables if needed
        await saver.setup()
        logger.info("AsyncPostgresSaver initialized successfully")
        yield saver

    logger.info("AsyncPostgresSaver connection closed")


# Legacy sync function for backwards compatibility (limited functionality)
def get_checkpointer(config: dict) -> Optional[object]:
    """
    DEPRECATED: Use create_checkpointer_context() for async support.

    This sync version only works with LangGraph's sync methods (invoke).
    For streaming (astream), you MUST use create_checkpointer_context().
    """
    checkpoint_config = config.get("checkpointing", {})

    if not checkpoint_config.get("enabled", False):
        logger.info("Checkpointing is disabled in configuration")
        return None

    backend = checkpoint_config.get("backend", "sqlite")

    if backend == "sqlite":
        return _init_sync_sqlite_checkpointer(checkpoint_config)
    elif backend == "postgres":
        logger.warning(
            "Sync PostgresSaver not recommended. Use create_checkpointer_context() instead."
        )
        return None
    else:
        raise ValueError(f"Unknown checkpointing backend: {backend}")


def _init_sync_sqlite_checkpointer(config: dict):
    """
    Initialize SYNC SqliteSaver for invoke-only workflows.

    WARNING: This does NOT support astream/ainvoke. Use only for testing
    or workflows that exclusively use sync invoke().
    """
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite not installed. Checkpointing DISABLED."
        )
        return None

    db_path = config.get("sqlite_path", "./data/checkpoints.db")

    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    logger.warning(
        f"Using SYNC SqliteSaver at: {db_path}. "
        "This does NOT support streaming (astream). "
        "Use create_checkpointer_context() for full async support."
    )

    conn = sqlite3.connect(db_path, check_same_thread=False)
    return SqliteSaver(conn)


def get_default_checkpointer():
    """
    Returns the default checkpointer for interrupt/resume support.

    ADR-CORE-042: Enables the "Raise Hand" pattern where any specialist
    can pause workflow execution to request user clarification.

    Currently returns MemorySaver (in-memory, no persistence).
    State survives for the duration of the process but is lost on restart.

    For persistent checkpointing (RECESS/ESM pattern), use
    create_checkpointer_context() with appropriate config instead.

    Future: This function can be extended to read from config to select
    backend (memory/sqlite/postgres) while keeping the call site unchanged.

    Returns:
        A LangGraph checkpointer instance (MemorySaver).
    """
    from langgraph.checkpoint.memory import MemorySaver
    logger.info("Initializing MemorySaver for in-memory checkpointing (ADR-CORE-042)")
    return MemorySaver()
