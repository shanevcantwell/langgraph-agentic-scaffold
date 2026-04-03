"""
Event bus for broadcasting raw LangGraph events to headless observers (#267).

This is the contract surface between the execution layer (which pushes events)
and the observability layer (which subscribes to them). The dependency direction
is execution -> observability: chat heads push, observability reads.
"""
import asyncio
from typing import Dict, List, Any


class EventBus:
    """
    Pub/sub for raw LangGraph events keyed by run_id.

    Producers call push() for each event.  Observers call subscribe() to get
    an asyncio.Queue, then read from it.  A sentinel ``None`` is pushed on
    close() to signal end-of-stream.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def push(self, run_id: str, event: Dict[str, Any]) -> None:
        async with self._lock:
            for q in self._subscribers.get(run_id, []):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # slow observer -- drop event rather than block producer

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    async def close(self, run_id: str) -> None:
        """Push sentinel and remove all subscribers for *run_id*."""
        async with self._lock:
            queues = self._subscribers.pop(run_id, [])
        for q in queues:
            try:
                q.put_nowait(None)  # sentinel
            except asyncio.QueueFull:
                pass


# Module-level singleton -- imported by both chat heads (push) and
# observability router (subscribe).
event_bus = EventBus()
