from __future__ import annotations

from pydantic import BaseModel, Field

from app.market_data.schemas.fund import FundSnapshot
from app.market_data.schemas.news import MarketEvent
from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import CapitalFlowSnapshot, IndexSnapshot, PriceCandle, QuoteSnapshot, TechnicalSnapshot
from app.market_data.schemas.sector import SectorSnapshot


class ScreenedStock(BaseModel):
    quote: QuoteSnapshot
    profile: SecurityProfile
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    score: float = 0.0


class RecommendationRequest(BaseModel):
    query: str
    risk_level: str = "medium"
    investment_horizon: str = "medium"
    analysis_mode: str = "professional"
    limit: int = 5


class RecommendationItem(BaseModel):
    symbol: str
    name: str
    current_price: float | None = None
    change_percent: float | None = None
    turnover: float | None = None
    attention_reason: str
    driver: str
    primary_risk: str
    style_fit: str
    action_tag: str
    capital_flow: str | None = None
    news_signal: str | None = None
    score: float


class RecommendationResponse(BaseModel):
    disclaimer: str
    market_regime: str
    market_view: str
    clarification_question: str | None = None
    clarification_options: list[str] = Field(default_factory=list)
    candidates: list[RecommendationItem] = Field(default_factory=list)
    screening_logic: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class DashboardOverview(BaseModel):
    indices: list[IndexSnapshot] = Field(default_factory=list)
    market_sentiment: dict[str, str | float] = Field(default_factory=dict)
    hot_sectors: list[SectorSnapshot] = Field(default_factory=list)
    top_gainers: list[QuoteSnapshot] = Field(default_factory=list)
    top_turnover: list[QuoteSnapshot] = Field(default_factory=list)
    hot_etfs: list[FundSnapshot] = Field(default_factory=list)
    latest_events: list[MarketEvent] = Field(default_factory=list)


class StockAnalysisResponse(BaseModel):
    quote: QuoteSnapshot
    technical: TechnicalSnapshot | None = None
    profile: SecurityProfile
    history: list[PriceCandle] = Field(default_factory=list)
    capital_flow: CapitalFlowSnapshot | None = None
    news: list[MarketEvent] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
