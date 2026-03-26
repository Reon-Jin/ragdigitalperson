from __future__ import annotations

from pydantic import BaseModel, Field


class QuoteSnapshot(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    timestamp: str
    last_price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    turnover: float | None = None
    amplitude: float | None = None
    turnover_rate: float | None = None


class PriceCandle(BaseModel):
    timestamp: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    turnover: float | None = None


class IndexSnapshot(BaseModel):
    symbol: str
    name: str
    market: str
    timestamp: str
    last_price: float
    change: float
    change_percent: float
    turnover: float | None = None


class TechnicalSnapshot(BaseModel):
    symbol: str
    timestamp: str
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    rsi14: float | None = None
    macd_diff: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    momentum_label: str = "neutral"


class CapitalFlowSnapshot(BaseModel):
    symbol: str
    timestamp: str
    main_net_inflow: float | None = None
    main_net_inflow_ratio: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    trend_label: str = "neutral"
    summary: str = ""


class QuoteResponse(BaseModel):
    quote: QuoteSnapshot
    technical: TechnicalSnapshot
    provider_meta: dict[str, str | bool]


class PrefetchResponse(BaseModel):
    symbol: str
    tasks: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
