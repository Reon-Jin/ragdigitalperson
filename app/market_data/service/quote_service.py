from __future__ import annotations

from app.config import Settings
from app.market_data.cache.request_deduper import RequestDeduper
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.quote import CapitalFlowSnapshot, PriceCandle, QuoteResponse, QuoteSnapshot


class QuoteService:
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

    async def get_snapshot(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        cache_key = f"quote:{market or self.settings.market_default_region}:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> QuoteSnapshot:
            quote = await self.registry.quote_chain.first_success("get_quote", symbol, market=market)
            await self.cache.set(cache_key, quote, ttl=self.settings.market_quote_cache_ttl_seconds)
            return quote

        return await self.deduper.run(cache_key, loader)

    async def get_quote_response(self, symbol: str, market: str | None = None) -> QuoteResponse:
        quote = await self.get_snapshot(symbol, market=market)
        technical = await self.registry.technical_chain.first_success("get_technical_snapshot", symbol, market=market)
        return QuoteResponse(
            quote=quote,
            technical=technical,
            provider_meta={
                "provider": "chain",
                "cached": False,
                "market_style": self.settings.market_style,
                "timestamp": quote.timestamp,
                "quote_provider": self.settings.market_primary_quote_provider,
                "technical_provider": self.settings.market_primary_technical_provider,
            },
        )

    async def get_history(self, symbol: str, market: str | None = None, limit: int = 60) -> list[PriceCandle]:
        cache_key = f"history:{market or self.settings.market_default_region}:{symbol}:{limit}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> list[PriceCandle]:
            history = await self.registry.quote_chain.first_success("get_history", symbol, market=market, limit=limit)
            await self.cache.set(cache_key, history, ttl=self.settings.market_board_cache_ttl_seconds)
            return history

        return await self.deduper.run(cache_key, loader)

    async def get_capital_flow(self, symbol: str, market: str | None = None) -> CapitalFlowSnapshot:
        cache_key = f"capital_flow:{market or self.settings.market_default_region}:{symbol}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        async def loader() -> CapitalFlowSnapshot:
            flow = await self.registry.quote_chain.first_success("get_capital_flow", symbol, market=market)
            await self.cache.set(cache_key, flow, ttl=self.settings.market_quote_cache_ttl_seconds)
            return flow

        return await self.deduper.run(cache_key, loader)
