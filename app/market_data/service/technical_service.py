from __future__ import annotations

from app.config import Settings
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.quote import TechnicalSnapshot


class TechnicalService:
    def __init__(
        self,
        registry: MarketDataProviderRegistry,
        cache: TTLCache,
        deduper: RequestDeduper,
        settings: Settings,
    ) -> None:
        self.registry = registry
        self.cache = cache
        self.deduper = deduper
        self.settings = settings

    async def get_snapshot(self, symbol: str, market: str | None = None) -> TechnicalSnapshot:
        cache_key = f"technical:{market or self.settings.market_default_region}:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> TechnicalSnapshot:
            technical = await self.registry.technical_chain.first_success("get_technical_snapshot", symbol, market=market)
            await self.cache.set(cache_key, technical, ttl=self.settings.market_quote_cache_ttl_seconds)
            return technical

        return await self.deduper.run(cache_key, loader)
