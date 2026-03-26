from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ConcurrencyGate:
    def __init__(self, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max(max_concurrency, 1))

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._semaphore:
            yield
