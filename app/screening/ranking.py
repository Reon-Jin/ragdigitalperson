from __future__ import annotations

from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import QuoteSnapshot


def score_stock(quote: QuoteSnapshot, profile: SecurityProfile) -> float:
    momentum = max((quote.change_percent or 0) + 5, 0)
    liquidity = min((quote.turnover or 0) / 10_000_000_000, 10)
    fundamentals = ((profile.roe or 0) / 5) + ((profile.dividend_yield or 0) / 2)
    leverage_penalty = (profile.debt_ratio or 0) / 25
    return round(momentum + liquidity + fundamentals - leverage_penalty, 2)
