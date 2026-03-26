from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from pydantic import BaseModel

from app.market_data.schemas.fund import FundSnapshot
from app.market_data.schemas.news import MarketEvent
from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import IndexSnapshot, QuoteSnapshot, TechnicalSnapshot
from app.market_data.schemas.sector import SectorSnapshot


class ProviderHealth(BaseModel):
    provider: str
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


class QuoteProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_quote(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        raise NotImplementedError

    async def get_quotes(self, symbols: Sequence[str], market: str | None = None) -> list[QuoteSnapshot]:
        return [await self.get_quote(symbol, market=market) for symbol in symbols]

    @abstractmethod
    async def get_indices(self, market: str | None = None) -> list[IndexSnapshot]:
        raise NotImplementedError

    @abstractmethod
    async def healthcheck(self) -> ProviderHealth:
        raise NotImplementedError


class FundamentalsProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_security_profile(self, symbol: str, market: str | None = None) -> SecurityProfile:
        raise NotImplementedError


class FundProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_fund(self, fund_code: str, market: str | None = None) -> FundSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def get_hot_funds(self, market: str | None = None, limit: int = 5) -> list[FundSnapshot]:
        raise NotImplementedError


class NewsProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_news(self, symbol: str | None = None, topic: str | None = None, limit: int = 5) -> list[MarketEvent]:
        raise NotImplementedError


class TechnicalIndicatorProvider(ABC):
    provider_name: str

    @abstractmethod
    async def get_technical_snapshot(self, symbol: str, market: str | None = None) -> TechnicalSnapshot:
        raise NotImplementedError


class ScreenerProvider(ABC):
    provider_name: str

    @abstractmethod
    async def screen_stocks(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def screen_funds(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def get_hot_sectors(self, market: str | None = None, limit: int = 6) -> list[SectorSnapshot]:
        raise NotImplementedError
