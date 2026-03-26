from __future__ import annotations

from app.config import Settings
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.news import MarketEvent


class NewsService:
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

    async def get_news(self, symbol: str | None = None, topic: str | None = None, limit: int = 5) -> list[MarketEvent]:
        cache_key = f"news:{symbol or topic or 'market'}:{limit}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> list[MarketEvent]:
            items = await self.registry.news_chain.first_success("get_news", symbol=symbol, topic=topic, limit=limit)
            await self.cache.set(cache_key, items, ttl=self.settings.market_news_cache_ttl_seconds)
            return items

        return await self.deduper.run(cache_key, loader)
