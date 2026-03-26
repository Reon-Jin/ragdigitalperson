from __future__ import annotations

from app.market_data.schemas.screening import RecommendationRequest, RecommendationResponse
from app.recommendation.recommendation_engine import RecommendationEngine


class RecommendationAPI:
    def __init__(self, recommendation_engine: RecommendationEngine) -> None:
        self.recommendation_engine = recommendation_engine

    async def recommend_stocks(self, payload: RecommendationRequest) -> RecommendationResponse:
        return await self.recommendation_engine.recommend_stocks(payload)
