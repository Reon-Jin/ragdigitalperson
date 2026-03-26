from __future__ import annotations

from pydantic import BaseModel


class SecurityProfile(BaseModel):
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_cap: float | None = None
    pe: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    debt_ratio: float | None = None
