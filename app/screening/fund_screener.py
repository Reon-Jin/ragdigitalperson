from __future__ import annotations

from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.fund import FundSnapshot
from app.market_data.service.fund_service import FundService


class FundScreener:
    def __init__(self, registry: MarketDataProviderRegistry, fund_service: FundService) -> None:
        self.registry = registry
        self.fund_service = fund_service

    async def screen(self, query: str, market: str | None = None, limit: int = 5) -> list[FundSnapshot]:
        codes = await self.registry.screener_chain.first_success("screen_funds", query, market=market, limit=limit)
        items = [await self.fund_service.get_fund(code, market=market) for code in codes]
        return sorted(items, key=lambda item: (item.recent_1m or 0) - (item.drawdown or 0), reverse=True)[:limit]
