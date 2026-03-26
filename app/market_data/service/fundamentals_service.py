from __future__ import annotations

from app.config import Settings
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.profile import SecurityProfile


class FundamentalsService:
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

    async def get_profile(self, symbol: str, market: str | None = None) -> SecurityProfile:
        cache_key = f"profile:{market or self.settings.market_default_region}:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> SecurityProfile:
            profile = await self.registry.fundamentals_chain.first_success("get_security_profile", symbol, market=market)
            await self.cache.set(cache_key, profile, ttl=self.settings.market_fundamentals_cache_ttl_seconds)
            return profile

        return await self.deduper.run(cache_key, loader)
