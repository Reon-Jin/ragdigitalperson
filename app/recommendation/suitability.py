from __future__ import annotations

from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import QuoteSnapshot


class SuitabilityService:
    def style_fit(self, risk_level: str, quote: QuoteSnapshot, profile: SecurityProfile) -> str:
        volatility = quote.amplitude or 0
        if risk_level == "low":
            return "稳健" if volatility <= 4 and (profile.dividend_yield or 0) >= 2 else "均衡"
        if risk_level == "high":
            return "激进" if volatility >= 4 else "均衡"
        return "均衡"

    def action_tag(self, risk_level: str, quote: QuoteSnapshot) -> str:
        move = quote.change_percent or 0
        if move >= 3:
            return "观察" if risk_level == "low" else "短期交易观察"
        if move >= 0.8:
            return "分批跟踪"
        if move <= -1.5:
            return "逢回调关注"
        return "中期跟踪"
