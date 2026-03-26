from __future__ import annotations

from pydantic import BaseModel, Field


class FundSnapshot(BaseModel):
    fund_code: str
    fund_name: str
    nav: float | None = None
    nav_date: str | None = None
    daily_change: float | None = None
    recent_1w: float | None = None
    recent_1m: float | None = None
    recent_3m: float | None = None
    drawdown: float | None = None
    category: str | None = None
    benchmark: str | None = None
    manager: str | None = None
    fee_rate: float | None = None
    style_exposure: list[str] = Field(default_factory=list)


class FundAnalysisResponse(BaseModel):
    snapshot: FundSnapshot
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class FundScreeningItem(BaseModel):
    fund_code: str
    fund_name: str
    category: str | None = None
    recent_1w: float | None = None
    recent_1m: float | None = None
    recent_3m: float | None = None
    drawdown: float | None = None
    style_fit: str
    reason: str
    risk: str


class FundScreeningResponse(BaseModel):
    disclaimer: str
    screening_logic: list[str] = Field(default_factory=list)
    items: list[FundScreeningItem] = Field(default_factory=list)
