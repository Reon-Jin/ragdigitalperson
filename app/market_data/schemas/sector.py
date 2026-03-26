from __future__ import annotations

from pydantic import BaseModel, Field


class SectorSnapshot(BaseModel):
    sector: str
    timestamp: str
    change_percent: float
    leader_symbol: str
    leader_name: str
    turnover: float | None = None
    heat_score: float = 0.0
    catalysts: list[str] = Field(default_factory=list)
