from __future__ import annotations

import asyncio

from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.service.quote_service import QuoteService
from app.market_data.schemas.screening import RecommendationRequest, RecommendationResponse
from app.recommendation.explanation_builder import ExplanationBuilder
from app.screening.stock_screener import StockScreener


class RecommendationEngine:
    def __init__(
        self,
        stock_screener: StockScreener,
        explanation_builder: ExplanationBuilder,
        quote_service: QuoteService,
        news_service: NewsService,
        news_curator: MarketNewsCurator,
    ) -> None:
        self.stock_screener = stock_screener
        self.explanation_builder = explanation_builder
        self.quote_service = quote_service
        self.news_service = news_service
        self.news_curator = news_curator

    async def recommend_stocks(self, payload: RecommendationRequest) -> RecommendationResponse:
        clarification = self._build_clarification(payload.query)
        if clarification is not None:
            return RecommendationResponse(
                disclaimer="当前需求还不够具体，先补全约束条件后再给候选会更可靠。",
                market_regime="unknown",
                market_view="Agent 需要先确认你的风险、期限和偏好，避免给出失真的候选清单。",
                clarification_question=clarification["question"],
                clarification_options=clarification["options"],
                candidates=[],
                screening_logic=[
                    "先确认风险承受能力、持有周期和是否接受高波动。",
                    "再根据行业偏好、股息偏好或成长偏好筛选候选。",
                    "最后结合实时行情、新闻和资金流向给出理由。",
                ],
                risk_notes=["需求过于宽泛时，任何直接推荐都容易偏离你的真实目标。"],
            )

        screened = await self.stock_screener.screen(payload.query, limit=payload.limit)
        items = [self.explanation_builder.build_item(stock, payload.risk_level) for stock in screened[: payload.limit]]
        if items:
            extras = await asyncio.gather(*(self._build_extra(item.symbol) for item in items))
            items = [item.model_copy(update=extra) for item, extra in zip(items, extras)]

        if any((item.change_percent or 0) > 1.2 for item in items):
            market_regime = "risk_on"
            market_view = "当前市场对强势方向更敏感，但需要同时确认新闻催化与资金流是否共振。"
        else:
            market_regime = "balanced"
            market_view = "当前更适合做条件筛选和分层候选，而不是直接押注单一方向。"
        return RecommendationResponse(
            disclaimer="以下仅基于当前公开数据、实时行情、新闻和资金流快照生成候选，不构成个性化投资建议。",
            market_regime=market_regime,
            market_view=market_view,
            candidates=items,
            screening_logic=[
                "优先筛出量价活跃、基本面不失真且与用户需求匹配的 A 股候选。",
                "对每只候选再叠加新闻催化和主力资金流向，避免只看涨跌幅。",
                "输出候选而不是唯一答案，同时明确主要风险和适配人群。",
            ],
            risk_notes=[
                "短线强势不等于后续一定继续上涨。",
                "资金流和新闻催化都可能快速反转，最好结合位置和估值一起判断。",
            ],
        )

    async def _build_extra(self, symbol: str) -> dict[str, str]:
        news, capital_flow = await asyncio.gather(
            self.news_service.get_news(symbol=symbol, limit=4),
            self.quote_service.get_capital_flow(symbol),
        )
        curated_news = self.news_curator.curate(news, limit=2, focus_symbol=symbol)
        return {
            "capital_flow": capital_flow.summary,
            "news_signal": curated_news[0].title if curated_news else "近期缺少高质量催化新闻",
        }

    def _build_clarification(self, query: str) -> dict[str, object] | None:
        text = str(query or "")
        broad_terms = ("买什么", "推荐股票", "给我推荐", "想买股票", "有哪些股票", "帮我选股")
        has_theme = any(token in text for token in ("红利", "高股息", "新能源", "半导体", "AI", "银行", "消费", "医药"))
        has_risk = any(token in text for token in ("稳健", "激进", "低风险", "高风险", "波动"))
        has_horizon = any(token in text for token in ("短期", "中期", "长期", "波段", "持有"))
        if len(text.strip()) >= 10 and sum([has_theme, has_risk, has_horizon]) >= 2:
            return None
        if not any(term in text for term in broad_terms) and len(text.strip()) >= 8:
            return None
        return {
            "question": "你更看重哪一类候选：高股息稳健、景气成长、短线强势，还是某个行业主题？最好再补充预期持有周期。",
            "options": ["高股息稳健", "景气成长", "短线强势", "指定行业主题"],
        }
