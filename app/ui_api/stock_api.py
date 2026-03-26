from __future__ import annotations

import asyncio

from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.screening import StockAnalysisResponse
from app.market_data.service.fundamentals_service import FundamentalsService
from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.service.quote_service import QuoteService


class StockAPI:
    def __init__(
        self,
        quote_service: QuoteService,
        fundamentals_service: FundamentalsService,
        news_service: NewsService,
        news_curator: MarketNewsCurator,
    ) -> None:
        self.quote_service = quote_service
        self.fundamentals_service = fundamentals_service
        self.news_service = news_service
        self.news_curator = news_curator

    async def analyze(self, symbol: str, market: str | None = None) -> StockAnalysisResponse:
        quote, technical, profile, news, history, capital_flow = await asyncio.gather(
            self.quote_service.get_snapshot(symbol, market=market),
            self.quote_service.registry.technical_chain.first_success("get_technical_snapshot", symbol, market=market),
            self.fundamentals_service.get_profile(symbol, market=market),
            self.news_service.get_news(symbol=symbol, limit=12),
            self.quote_service.get_history(symbol, market=market, limit=60),
            self.quote_service.get_capital_flow(symbol, market=market),
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

    def _merge_quote_identity(self, profile: SecurityProfile, quote_name: str | None) -> SecurityProfile:
        if not quote_name:
            return profile
        if profile.company_name and not profile.company_name.startswith("模拟标的"):
            return profile
        return profile.model_copy(update={"company_name": quote_name})
