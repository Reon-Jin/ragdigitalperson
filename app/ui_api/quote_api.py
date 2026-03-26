from __future__ import annotations

from app.market_data.schemas.quote import QuoteResponse
from app.market_data.service.quote_service import QuoteService


class QuoteAPI:
    def __init__(self, quote_service: QuoteService) -> None:
        self.quote_service = quote_service

    async def get_quote(self, symbol: str, market: str | None = None) -> QuoteResponse:
        return await self.quote_service.get_quote_response(symbol, market=market)
