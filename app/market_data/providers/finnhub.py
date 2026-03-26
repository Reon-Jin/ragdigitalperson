from __future__ import annotations

from app.market_data.providers.base import (
    FundamentalsProvider,
    NewsProvider,
    ProviderHealth,
    QuoteProvider,
    TechnicalIndicatorProvider,
)


class FinnhubAdapter(QuoteProvider, FundamentalsProvider, NewsProvider, TechnicalIndicatorProvider):
    provider_name = "finnhub"

    async def get_quote(self, symbol: str, market: str | None = None):
        raise NotImplementedError("FinnhubAdapter is reserved for the next integration step.")

    async def get_indices(self, market: str | None = None):
        raise NotImplementedError("FinnhubAdapter is reserved for the next integration step.")

    async def get_security_profile(self, symbol: str, market: str | None = None):
        raise NotImplementedError("FinnhubAdapter is reserved for the next integration step.")

    async def get_news(self, symbol: str | None = None, topic: str | None = None, limit: int = 5):
        raise NotImplementedError("FinnhubAdapter is reserved for the next integration step.")

    async def get_technical_snapshot(self, symbol: str, market: str | None = None):
        raise NotImplementedError("FinnhubAdapter is reserved for the next integration step.")

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, ok=False, error="not implemented")
