from __future__ import annotations

from app.market_data.schemas.screening import DashboardOverview
from app.market_data.service.dashboard_service import DashboardService


class DashboardAPI:
    def __init__(self, dashboard_service: DashboardService) -> None:
        self.dashboard_service = dashboard_service

    async def overview(self, market: str | None = None) -> DashboardOverview:
        return await self.dashboard_service.get_overview(market=market)
