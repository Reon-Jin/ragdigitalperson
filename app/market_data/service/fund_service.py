from __future__ import annotations

from app.config import Settings
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.fund import FundSnapshot


class FundService:
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

    async def get_fund(self, fund_code: str, market: str | None = None) -> FundSnapshot:
        cache_key = f"fund:{market or self.settings.market_default_region}:{fund_code}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> FundSnapshot:
            fund = await self.registry.fund_chain.first_success("get_fund", fund_code, market=market)
            await self.cache.set(cache_key, fund, ttl=self.settings.market_board_cache_ttl_seconds)
            return fund

        return await self.deduper.run(cache_key, loader)

    async def get_hot_funds(self, market: str | None = None, limit: int = 5) -> list[FundSnapshot]:
        cache_key = f"fund-hot:{market or self.settings.market_default_region}:{limit}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached
        funds = await self.registry.fund_chain.first_success("get_hot_funds", market=market, limit=limit)
        await self.cache.set(cache_key, funds, ttl=self.settings.market_board_cache_ttl_seconds)
        return funds
