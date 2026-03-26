from __future__ import annotations

from app.market_data.schemas.fund import FundAnalysisResponse, FundScreeningItem, FundScreeningResponse
from app.market_data.service.fund_service import FundService
from app.screening.fund_screener import FundScreener


class FundAPI:
    def __init__(self, fund_service: FundService, fund_screener: FundScreener) -> None:
        self.fund_service = fund_service
        self.fund_screener = fund_screener

    async def analyze(self, fund_code: str, market: str | None = None) -> FundAnalysisResponse:
        snapshot = await self.fund_service.get_fund(fund_code, market=market)
        highlights = [
            f"近 1 周 {snapshot.recent_1w or 0:.2f}%，近 1 月 {snapshot.recent_1m or 0:.2f}%，近 3 月 {snapshot.recent_3m or 0:.2f}%。",
            f"当前回撤约 {snapshot.drawdown or 0:.2f}%，类别为 {snapshot.category or '基金 / ETF'}，适合结合波动承受能力一起看。",
            f"若有可得持仓风格，则优先观察 {', '.join(snapshot.style_exposure or ['指数跟踪'])} 的暴露是否与你的风险偏好匹配。",
        ]
        risks = [
            "基金和 ETF 的风格暴露会随市场切换而放大波动，历史回撤不代表未来风险已经释放完毕。",
            "若近期收益主要由单一主题驱动，需警惕拥挤交易和回撤放大。",
            "以下分析基于公开数据与基金快照，不构成个性化投资建议。",
        ]
        return FundAnalysisResponse(snapshot=snapshot, highlights=highlights, risks=risks)

    async def screen(
        self,
        query: str,
        risk_level: str = "medium",
        market: str | None = None,
        limit: int = 5,
    ) -> FundScreeningResponse:
        snapshots = await self.fund_screener.screen(query, market=market, limit=limit)
        items: list[FundScreeningItem] = []
        for snapshot in snapshots:
            drawdown = snapshot.drawdown or 0
            if drawdown <= 6:
                style_fit = "稳健"
            elif drawdown <= 12 and risk_level != "low":
                style_fit = "均衡"
            else:
                style_fit = "偏进取 / 需谨慎"

            items.append(
                FundScreeningItem(
                    fund_code=snapshot.fund_code,
                    fund_name=snapshot.fund_name,
                    category=snapshot.category,
                    recent_1w=snapshot.recent_1w,
                    recent_1m=snapshot.recent_1m,
                    recent_3m=snapshot.recent_3m,
                    drawdown=snapshot.drawdown,
                    style_fit=style_fit,
                    reason=(
                        f"近 1 月 {snapshot.recent_1m or 0:.2f}% / 近 3 月 {snapshot.recent_3m or 0:.2f}%，"
                        f"回撤约 {drawdown:.2f}%。"
                    ),
                    risk="若主题过于集中或行业风格切换，净值波动可能明显放大。",
                )
            )

        return FundScreeningResponse(
            disclaimer="以下结果仅基于当前公开净值、行情快照和筛选规则，不构成个性化投资建议。",
            screening_logic=[
                "优先关注近 1 月与近 3 月表现相对平衡、回撤可控、成交活跃的基金 / ETF。",
                "结合回撤、收益区间和风格暴露做适配性判断，而不是只看单日涨幅。",
            ],
            items=items,
        )
