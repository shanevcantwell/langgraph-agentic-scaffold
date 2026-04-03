# app/src/observability/__init__.py
"""Observability layer for LAS workflow execution.

Provides:
- Event bus: pub/sub for raw LangGraph events (contract between execution and observation)
- Active runs registry: shared state for run discovery
- Observability API router: FastAPI endpoints for monitoring, traces, archives
- Training data capture: specialist execution recording for fine-tuning
"""

from .training_capture import TrainingCapture, CapturedExecution, OutcomeStatus
from .event_bus import event_bus, EventBus
from .active_runs import active_runs, ActiveRunRegistry
from .router import router as observability_router, init as init_observability

__all__ = [
    # Training capture
    "TrainingCapture", "CapturedExecution", "OutcomeStatus",
    # Event bus (contract surface)
    "event_bus", "EventBus",
    # Active runs registry (shared state)
    "active_runs", "ActiveRunRegistry",
    # API router
    "observability_router", "init_observability",
]
