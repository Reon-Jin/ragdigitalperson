from __future__ import annotations

from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import QuoteSnapshot


def dividend_candidate(profile: SecurityProfile) -> bool:
    return (profile.dividend_yield or 0) >= 2.0


def low_volatility_candidate(quote: QuoteSnapshot) -> bool:
    return (quote.amplitude or 0) <= 4.5
