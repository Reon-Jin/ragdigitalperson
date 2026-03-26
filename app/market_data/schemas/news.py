from __future__ import annotations

from pydantic import BaseModel, Field


class MarketEvent(BaseModel):
    title: str
    source: str
    publish_time: str
    related_symbols: list[str] = Field(default_factory=list)
    event_type: str
    summary: str
    theme: str | None = None
    importance_score: float | None = None
    agent_reason: str | None = None
    action_hint: str | None = None
