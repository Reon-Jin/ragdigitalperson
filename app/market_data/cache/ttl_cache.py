from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def get_stale(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if not entry:
            return None
        return entry[1]

    async def set(self, key: str, value: Any, ttl: int) -> None:
        self._store[key] = (time.time() + max(ttl, 1), value)

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)
