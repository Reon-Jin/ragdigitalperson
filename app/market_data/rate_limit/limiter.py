from __future__ import annotations

import asyncio
import time


class QPSLimiter:
    def __init__(self, qps: int) -> None:
        self.qps = max(qps, 1)
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            window_start = now - 1
            self._timestamps = [value for value in self._timestamps if value >= window_start]
            if len(self._timestamps) >= self.qps:
                wait_seconds = max(self._timestamps[0] + 1 - now, 0.01)
                await asyncio.sleep(wait_seconds)
                now = time.time()
                window_start = now - 1
                self._timestamps = [value for value in self._timestamps if value >= window_start]
            self._timestamps.append(time.time())
