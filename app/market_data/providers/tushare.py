from __future__ import annotations

from app.market_data.providers.base import (
    FundProvider,
    FundamentalsProvider,
    ProviderHealth,
    QuoteProvider,
    ScreenerProvider,
)


class TushareAdapter(QuoteProvider, FundamentalsProvider, FundProvider, ScreenerProvider):
    provider_name = "tushare"

    async def get_quote(self, symbol: str, market: str | None = None):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def get_indices(self, market: str | None = None):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def get_security_profile(self, symbol: str, market: str | None = None):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def get_fund(self, fund_code: str, market: str | None = None):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def get_hot_funds(self, market: str | None = None, limit: int = 5):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def screen_stocks(self, query: str, market: str | None = None, limit: int = 5):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def screen_funds(self, query: str, market: str | None = None, limit: int = 5):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def get_hot_sectors(self, market: str | None = None, limit: int = 6):
        raise NotImplementedError("TushareAdapter is reserved for the next integration step.")

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, ok=False, error="not implemented")
