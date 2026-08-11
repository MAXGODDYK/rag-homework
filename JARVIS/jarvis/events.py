from __future__ import annotations

import asyncio
from collections import defaultdict

from .models import Event


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, user_id: str) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers[user_id].add(queue)
        return queue

    async def unsubscribe(self, user_id: str, queue: asyncio.Queue[Event]) -> None:
        async with self._lock:
            self._subscribers[user_id].discard(queue)
            if not self._subscribers[user_id]:
                self._subscribers.pop(user_id, None)

    async def publish(self, user_id: str, event: Event) -> None:
        async with self._lock:
            queues = tuple(self._subscribers.get(user_id, ()))
        for queue in queues:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
