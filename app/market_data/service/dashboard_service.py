from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings
from app.market_data.cache.ttl_cache import TTLCache
from app.market_data.providers.registry import MarketDataProviderRegistry
from app.market_data.schemas.screening import DashboardOverview
from app.market_data.service.fund_service import FundService
from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.service.quote_service import QuoteService


class DashboardService:
    def __init__(
        self,
        registry: MarketDataProviderRegistry,
        quote_service: QuoteService,
        fund_service: FundService,
        news_service: NewsService,
        news_curator: MarketNewsCurator,
        cache: TTLCache,
        settings: Settings,
    ) -> None:
        self.registry = registry
        self.quote_service = quote_service
        self.fund_service = fund_service
        self.news_service = news_service
        self.news_curator = news_curator
        self.cache = cache
        self.settings = settings

    async def get_overview(self, market: str | None = None) -> DashboardOverview:
        region = market or self.settings.market_default_region
        cache_key = f"dashboard:{region}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        indices = await self._load_fast_indices(region)
        market_sentiment = self._build_market_sentiment(indices)

        hot_sectors, top_gainers, top_turnover, hot_etfs, latest_events = await asyncio.gather(
            self._load_cached_or_timeout(
                key=f"dashboard:hot_sectors:{region}",
                loader=lambda: self.registry.screener_chain.first_success("get_hot_sectors", market=region, limit=6),
                timeout=0.9,
                ttl=self.settings.market_board_cache_ttl_seconds,
                default=[],
            ),
            self._load_cached_or_timeout(
                key=f"dashboard:top_gainers:{region}",
                loader=lambda: asyncio.gather(
                    *(self.quote_service.get_snapshot(symbol, market=region) for symbol in ("300750", "688981", "002594", "600519"))
                ),
                timeout=0.9,
                ttl=self.settings.market_board_cache_ttl_seconds,
                default=[],
            ),
            self._load_cached_or_timeout(
                key=f"dashboard:top_turnover:{region}",
                loader=lambda: asyncio.gather(
                    *(self.quote_service.get_snapshot(symbol, market=region) for symbol in ("600519", "601318", "600036", "000858"))
                ),
                timeout=0.9,
                ttl=self.settings.market_board_cache_ttl_seconds,
                default=[],
            ),
            self._load_cached_or_timeout(
                key=f"dashboard:hot_etfs:{region}",
                loader=lambda: self.fund_service.get_hot_funds(market=region, limit=4),
                timeout=1.0,
                ttl=self.settings.market_board_cache_ttl_seconds,
                default=[],
            ),
            self._load_cached_or_timeout(
                key=f"dashboard:events:{region}",
                loader=lambda: self._load_curated_events(region),
                timeout=1.4,
                ttl=self.settings.market_news_cache_ttl_seconds,
                default=[],
            ),
        )

        result = DashboardOverview(
            indices=indices,
            market_sentiment=market_sentiment,
            hot_sectors=hot_sectors,
            top_gainers=top_gainers,
            top_turnover=top_turnover,
            hot_etfs=hot_etfs,
            latest_events=latest_events,
        )
        await self.cache.set(cache_key, result, ttl=self.settings.market_board_cache_ttl_seconds)
        return result

    async def _load_curated_events(self, region: str) -> list[Any]:
        topic = "A股" if region == "CN" else "market"
        events = await self.news_service.get_news(topic=topic, limit=20)
        return self.news_curator.curate(events, limit=4)

    async def _load_fast_indices(self, region: str) -> list[Any]:
        return await self._load_cached_or_timeout(
            key=f"dashboard:indices:{region}",
            loader=lambda: self.registry.quote_chain.first_success("get_indices", market=region),
            timeout=0.7,
            ttl=self.settings.market_quote_cache_ttl_seconds,
            default=[],
        )

    async def _load_cached_or_timeout(
        self,
        *,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        timeout: float,
        ttl: int,
        default: Any,
    ) -> Any:
        fresh = await self.cache.get(key)
        if fresh is not None:
            return fresh

        stale = await self.cache.get_stale(key)
        try:
            value = await asyncio.wait_for(loader(), timeout=timeout)
            await self.cache.set(key, value, ttl=ttl)
            return value
        except Exception:
            return stale if stale is not None else default

    def _build_market_sentiment(self, indices: list[Any]) -> dict[str, str | float]:
        avg_index_move = round(sum((item.change_percent or 0) for item in indices) / max(len(indices), 1), 2) if indices else 0.0
        if avg_index_move >= 0.5:
            market_regime = "risk_on"
            market_summary = "市场风险偏好回暖，强势方向更活跃。"
        elif avg_index_move <= -0.5:
            market_regime = "defensive"
            market_summary = "市场偏防御，适合先等待确认信号。"
        else:
            market_regime = "balanced"
            market_summary = "市场处于均衡状态，更适合精选和分批观察。"
        return {
            "regime": market_regime,
            "summary": market_summary,
            "avg_index_move": avg_index_move,
            "style": self.settings.market_style,
        }
