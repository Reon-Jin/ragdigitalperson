from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class ProviderChain:
    def __init__(self, providers: list[Any]) -> None:
        self.providers = providers

    async def first_success(self, operation_name: str, *args: Any, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                operation: Callable[..., Awaitable[Any]] = getattr(provider, operation_name)
            except AttributeError as exc:
                last_error = exc
                continue
            try:
                return await operation(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - fallback path
                last_error = exc
                continue
        if last_error is None:
            raise RuntimeError("No providers registered.")
        raise RuntimeError(f"all providers failed for {operation_name}: {last_error}") from last_error
