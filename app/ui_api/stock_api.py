from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable

from app.config import Settings
from app.market_data.schemas.news import MarketEvent
from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import CapitalFlowSnapshot, TechnicalSnapshot
from app.market_data.schemas.screening import StockAnalysisResponse
from app.market_data.service.fundamentals_service import FundamentalsService
from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.service.quote_service import QuoteService
from app.market_data.service.technical_service import TechnicalService


class StockAPI:
    def __init__(
        self,
        quote_service: QuoteService,
        fundamentals_service: FundamentalsService,
        news_service: NewsService,
        news_curator: MarketNewsCurator,
        technical_service: TechnicalService,
        settings: Settings,
    ) -> None:
        self.quote_service = quote_service
        self.fundamentals_service = fundamentals_service
        self.news_service = news_service
        self.news_curator = news_curator
        self.technical_service = technical_service
        self.settings = settings

    async def analyze(self, symbol: str, market: str | None = None) -> StockAnalysisResponse:
        quote = await asyncio.wait_for(
            self.quote_service.get_snapshot(symbol, market=market),
            timeout=self.settings.market_analysis_quote_timeout_seconds,
        )

        technical, profile, news, history, capital_flow = await asyncio.gather(
            self._fallback_after_timeout(
                self.technical_service.get_snapshot(symbol, market=market),
                timeout=self.settings.market_analysis_component_timeout_seconds,
                default=self._default_technical(symbol, quote.timestamp),
            ),
            self._fallback_after_timeout(
                self.fundamentals_service.get_profile(symbol, market=market),
                timeout=self.settings.market_analysis_component_timeout_seconds,
                default=self._default_profile(symbol, quote.name, market),
            ),
            self._fallback_after_timeout(
                self.news_service.get_news(symbol=symbol, limit=8),
                timeout=self.settings.market_analysis_component_timeout_seconds,
                default=[],
            ),
            self._fallback_after_timeout(
                self.quote_service.get_history(symbol, market=market, limit=60),
                timeout=self.settings.market_analysis_history_timeout_seconds,
                default=[],
            ),
            self._fallback_after_timeout(
                self.quote_service.get_capital_flow(symbol, market=market),
                timeout=self.settings.market_analysis_component_timeout_seconds,
                default=self._default_capital_flow(symbol, quote.timestamp),
            ),
        )

        profile = self._merge_quote_identity(profile, quote.name)
        curated_news = self.news_curator.curate(news, limit=5, focus_symbol=symbol)
        turnover_billion = round((quote.turnover or 0) / 100000000, 2)
        highlights = [
            f"当前涨跌幅 {quote.change_percent or 0:.2f}%，成交额约 {turnover_billion:.2f} 亿元，适合先看量价是否延续。",
            f"{profile.company_name} 所属 {profile.sector or '待补充'} / {profile.industry or '待补充'}，估值约 PE {profile.pe or 0:.2f}、PB {profile.pb or 0:.2f}。",
            f"盈利能力参考 ROE {profile.roe or 0:.2f}%，若后续财报验证不及预期，短线情绪可能回落。",
            capital_flow.summary,
        ]
        risks = [
            "当前分析基于公开行情、基本面快照和近期资讯，不构成个性化投资建议。",
            "若成交放大但价格无法继续抬升，需警惕短线资金兑现带来的回撤。",
            "行业政策、财报落地和市场风格切换，都会影响后续表现。",
            f"近期重点事件：{curated_news[0].title}" if curated_news else "近期缺少高质量新闻，建议同时核对公告。",
        ]
        return StockAnalysisResponse(
            quote=quote,
            technical=technical,
            profile=profile,
            history=history,
            capital_flow=capital_flow,
            news=curated_news,
            highlights=highlights,
            risks=risks,
        )

    async def _fallback_after_timeout(self, awaitable: Awaitable[Any], *, timeout: float, default: Any) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except Exception:
            return default

    def _default_profile(self, symbol: str, quote_name: str | None, market: str | None) -> SecurityProfile:
        return SecurityProfile(
            symbol=symbol,
            company_name=quote_name or symbol,
            sector=None,
            industry=None,
            exchange=market or "CN",
            market_cap=None,
            pe=None,
            pb=None,
            dividend_yield=None,
            roe=None,
            debt_ratio=None,
        )

    def _default_technical(self, symbol: str, timestamp: str) -> TechnicalSnapshot:
        return TechnicalSnapshot(symbol=symbol, timestamp=timestamp, momentum_label="neutral")

    def _default_capital_flow(self, symbol: str, timestamp: str) -> CapitalFlowSnapshot:
        return CapitalFlowSnapshot(symbol=symbol, timestamp=timestamp, trend_label="neutral", summary="资金流数据暂不可用。")

    def _merge_quote_identity(self, profile: SecurityProfile, quote_name: str | None) -> SecurityProfile:
        if not quote_name:
            return profile
        if profile.company_name and not profile.company_name.startswith("模拟标的"):
            return profile
        return profile.model_copy(update={"company_name": quote_name})
