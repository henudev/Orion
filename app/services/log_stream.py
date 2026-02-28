from __future__ import annotations

import asyncio
from collections import defaultdict


class LogBroker:
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        async with self._lock:
            self._channels[channel].add(queue)
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            subscribers = self._channels.get(channel)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._channels.pop(channel, None)

    async def publish(self, channel: str, line: str) -> None:
        async with self._lock:
            subscribers = list(self._channels.get(channel, set()))
        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(line)


log_broker = LogBroker()

