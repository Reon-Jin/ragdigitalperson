from __future__ import annotations

from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.screening import ScreenedStock
from app.market_data.service.fundamentals_service import FundamentalsService
from app.market_data.service.quote_service import QuoteService
from app.screening.filters import dividend_candidate, low_volatility_candidate
from app.screening.ranking import score_stock
from app.services.stock_resolver import StockResolver


class StockScreener:
    def __init__(
        self,
        registry: MarketDataProviderRegistry,
        quote_service: QuoteService,
        fundamentals_service: FundamentalsService,
        stock_resolver: StockResolver | None = None,
    ) -> None:
        self.registry = registry
        self.quote_service = quote_service
        self.fundamentals_service = fundamentals_service
        self.stock_resolver = stock_resolver

    async def screen(self, query: str, market: str | None = None, limit: int = 5) -> list[ScreenedStock]:
        direct_symbol = await self._resolve_direct_symbol(query)
        if direct_symbol:
            symbols = [direct_symbol]
        else:
            symbols = await self.registry.screener_chain.first_success("screen_stocks", query, market=market, limit=limit)
        results: list[ScreenedStock] = []
        for symbol in symbols:
            quote = await self.quote_service.get_snapshot(symbol, market=market)
            profile = await self.fundamentals_service.get_profile(symbol, market=market)
            reasons: list[str] = []
            risks: list[str] = []
            if dividend_candidate(profile):
                reasons.append("股息率处于可关注区间")
            if low_volatility_candidate(quote):
                reasons.append("日内振幅相对可控")
            if (quote.change_percent or 0) > 1.5:
                reasons.append("短线强度较好")
            if (profile.debt_ratio or 0) > 60:
                risks.append("资产负债率偏高")
            if (quote.amplitude or 0) > 6:
                risks.append("波动明显放大")
            results.append(
                ScreenedStock(
                    quote=quote,
                    profile=profile,
                    reasons=reasons or ["市场关注度提升"],
                    risks=risks or ["需要结合后续公告验证"],
                    score=score_stock(quote, profile),
                )
            )
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    async def _resolve_direct_symbol(self, query: str) -> str | None:
        if self.stock_resolver is None:
            return None
        symbol = self.stock_resolver.extract_symbol(query)
        if symbol:
            return symbol
        resolved = await self.stock_resolver.resolve(query)
        return resolved.symbol if resolved else None
