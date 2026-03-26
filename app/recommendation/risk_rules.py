from __future__ import annotations

from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import QuoteSnapshot


class RiskRules:
    def primary_risk(self, quote: QuoteSnapshot, profile: SecurityProfile) -> str:
        if (profile.debt_ratio or 0) >= 60:
            return "杠杆压力偏高，后续业绩波动可能放大估值压力。"
        if (quote.amplitude or 0) >= 6:
            return "短线波动较大，追价的回撤风险更高。"
        if (profile.pe or 0) >= 35:
            return "估值不低，需要后续业绩继续兑现。"
        return "当前逻辑仍需后续公告和资金持续性验证。"
