from __future__ import annotations

from app.market_data.schemas.screening import RecommendationItem, ScreenedStock
from app.recommendation.risk_rules import RiskRules
from app.recommendation.suitability import SuitabilityService


class ExplanationBuilder:
    def __init__(self, suitability: SuitabilityService, risk_rules: RiskRules) -> None:
        self.suitability = suitability
        self.risk_rules = risk_rules

    def build_item(self, stock: ScreenedStock, risk_level: str) -> RecommendationItem:
        style_fit = self.suitability.style_fit(risk_level, stock.quote, stock.profile)
        return RecommendationItem(
            symbol=stock.quote.symbol,
            name=stock.quote.name,
            current_price=stock.quote.last_price,
            change_percent=stock.quote.change_percent,
            turnover=stock.quote.turnover,
            attention_reason=stock.reasons[0],
            driver=stock.reasons[1] if len(stock.reasons) > 1 else "资金活跃度与基本面稳定性较匹配",
            primary_risk=self.risk_rules.primary_risk(stock.quote, stock.profile),
            style_fit=style_fit,
            action_tag=self.suitability.action_tag(risk_level, stock.quote),
            score=stock.score,
        )
