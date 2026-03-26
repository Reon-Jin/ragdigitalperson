from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class RequestDeduper:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def run(self, key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
        async with self._lock:
            existing = self._inflight.get(key)
            if existing:
                future = existing
            else:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
        if existing:
            return await future

        try:
            value = await loader()
            future.set_result(value)
            return value
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
