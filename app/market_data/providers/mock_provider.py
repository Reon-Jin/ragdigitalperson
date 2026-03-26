from __future__ import annotations

from datetime import datetime
from random import Random

from app.market_data.providers.base import (
    FundProvider,
    FundamentalsProvider,
    NewsProvider,
    ProviderHealth,
    QuoteProvider,
    ScreenerProvider,
    TechnicalIndicatorProvider,
)
from app.market_data.schemas.fund import FundSnapshot
from app.market_data.schemas.news import MarketEvent
from app.market_data.schemas.profile import SecurityProfile
from app.market_data.schemas.quote import CapitalFlowSnapshot, IndexSnapshot, PriceCandle, QuoteSnapshot, TechnicalSnapshot
from app.market_data.schemas.sector import SectorSnapshot


MOCK_STOCK_UNIVERSE = {
    "600519": ("贵州茅台", "消费", "白酒"),
    "000858": ("五粮液", "消费", "白酒"),
    "300750": ("宁德时代", "新能源", "锂电池"),
    "002594": ("比亚迪", "新能源", "汽车整车"),
    "601318": ("中国平安", "金融", "保险"),
    "600036": ("招商银行", "金融", "银行"),
    "688981": ("中芯国际", "科技", "半导体"),
    "600900": ("长江电力", "红利", "公用事业"),
}

MOCK_FUNDS = {
    "510300": ("沪深300ETF", "ETF", "沪深300"),
    "510880": ("红利ETF", "ETF", "中证红利"),
    "159915": ("创业板ETF", "ETF", "创业板"),
    "161725": ("招商中证白酒", "指数基金", "中证白酒"),
}


class MockMarketDataAdapter(
    QuoteProvider,
    FundamentalsProvider,
    FundProvider,
    NewsProvider,
    TechnicalIndicatorProvider,
    ScreenerProvider,
):
    provider_name = "mock"

    def _rng(self, key: str) -> Random:
        today = datetime.now().strftime("%Y%m%d")
        return Random(f"{today}:{key}")

    def _ts(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    async def get_quote(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        name, _, _ = MOCK_STOCK_UNIVERSE.get(symbol, (f"模拟标的{symbol}", "综合", "未知"))
        rng = self._rng(f"quote:{symbol}")
        prev_close = round(rng.uniform(18, 320), 2)
        change_percent = round(rng.uniform(-4.5, 5.8), 2)
        change = round(prev_close * change_percent / 100, 2)
        last_price = round(prev_close + change, 2)
        high = round(max(last_price, prev_close) * rng.uniform(1.0, 1.03), 2)
        low = round(min(last_price, prev_close) * rng.uniform(0.97, 1.0), 2)
        open_price = round(rng.uniform(low, high), 2)
        volume = round(rng.uniform(8_000_000, 220_000_000), 2)
        turnover = round(volume * last_price, 2)
        amplitude = round((high - low) / max(prev_close, 0.01) * 100, 2)
        return QuoteSnapshot(
            symbol=symbol,
            name=name,
            market=market or "CN",
            currency="CNY",
            timestamp=self._ts(),
            last_price=last_price,
            change=change,
            change_percent=change_percent,
            open=open_price,
            high=high,
            low=low,
            prev_close=prev_close,
            volume=volume,
            turnover=turnover,
            amplitude=amplitude,
            turnover_rate=round(rng.uniform(0.4, 8.2), 2),
        )

    async def get_indices(self, market: str | None = None) -> list[IndexSnapshot]:
        items = [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指")]
        result: list[IndexSnapshot] = []
        for symbol, name in items:
            rng = self._rng(f"index:{symbol}")
            last_price = round(rng.uniform(2500, 12500), 2)
            change_percent = round(rng.uniform(-2.2, 2.8), 2)
            result.append(
                IndexSnapshot(
                    symbol=symbol,
                    name=name,
                    market=market or "CN",
                    timestamp=self._ts(),
                    last_price=last_price,
                    change=round(last_price * change_percent / 100, 2),
                    change_percent=change_percent,
                    turnover=round(rng.uniform(90_000_000_000, 780_000_000_000), 2),
                )
            )
        return result

    async def get_history(self, symbol: str, market: str | None = None, limit: int = 60) -> list[PriceCandle]:
        quote = await self.get_quote(symbol, market=market)
        base = quote.last_price or quote.prev_close or 20.0
        rng = self._rng(f"history:{symbol}")
        history: list[PriceCandle] = []
        current = base * 0.9
        for index in range(limit):
            drift = rng.uniform(-0.03, 0.035)
            open_price = round(current, 2)
            close = round(max(0.5, open_price * (1 + drift)), 2)
            high = round(max(open_price, close) * rng.uniform(1.0, 1.02), 2)
            low = round(min(open_price, close) * rng.uniform(0.98, 1.0), 2)
            current = close
            history.append(
                PriceCandle(
                    timestamp=f"D-{limit - index - 1}",
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=round(rng.uniform(5_000_000, 60_000_000), 2),
                    turnover=round(rng.uniform(300_000_000, 6_000_000_000), 2),
                )
            )
        return history

    async def get_capital_flow(self, symbol: str, market: str | None = None) -> CapitalFlowSnapshot:
        rng = self._rng(f"capital:{symbol}")
        main = round(rng.uniform(-6.5, 8.8) * 100000000, 2)
        ratio = round(rng.uniform(-12, 15), 2)
        if main > 0:
            trend = "inflow"
            summary = "模拟主力资金偏流入，说明短线情绪更积极。"
        elif main < 0:
            trend = "outflow"
            summary = "模拟主力资金偏流出，说明短线存在兑现压力。"
        else:
            trend = "neutral"
            summary = "模拟资金流向中性。"
        return CapitalFlowSnapshot(
            symbol=symbol,
            timestamp=self._ts(),
            main_net_inflow=main,
            main_net_inflow_ratio=ratio,
            super_large_net_inflow=round(main * 0.45, 2),
            large_net_inflow=round(main * 0.22, 2),
            medium_net_inflow=round(-main * 0.15, 2),
            small_net_inflow=round(-main * 0.52, 2),
            trend_label=trend,
            summary=summary,
        )

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self.provider_name, ok=True, latency_ms=5)

    async def get_security_profile(self, symbol: str, market: str | None = None) -> SecurityProfile:
        name, sector, industry = MOCK_STOCK_UNIVERSE.get(symbol, (f"模拟标的{symbol}", "综合", "未知"))
        rng = self._rng(f"profile:{symbol}")
        return SecurityProfile(
            symbol=symbol,
            company_name=name,
            sector=sector,
            industry=industry,
            exchange="SSE" if symbol.startswith("6") else "SZSE",
            market_cap=round(rng.uniform(30_000_000_000, 2_400_000_000_000), 2),
            pe=round(rng.uniform(8, 42), 2),
            pb=round(rng.uniform(0.9, 8.5), 2),
            dividend_yield=round(rng.uniform(0.2, 6.0), 2),
            roe=round(rng.uniform(4.0, 24.0), 2),
            debt_ratio=round(rng.uniform(8.0, 72.0), 2),
        )

    async def get_fund(self, fund_code: str, market: str | None = None) -> FundSnapshot:
        name, category, benchmark = MOCK_FUNDS.get(fund_code, (f"模拟基金{fund_code}", "混合基金", "自定义基准"))
        rng = self._rng(f"fund:{fund_code}")
        return FundSnapshot(
            fund_code=fund_code,
            fund_name=name,
            nav=round(rng.uniform(0.8, 4.3), 4),
            nav_date=datetime.now().strftime("%Y-%m-%d"),
            daily_change=round(rng.uniform(-2.5, 2.8), 2),
            recent_1w=round(rng.uniform(-4.0, 5.2), 2),
            recent_1m=round(rng.uniform(-8.0, 11.0), 2),
            recent_3m=round(rng.uniform(-12.0, 18.0), 2),
            drawdown=round(rng.uniform(2.0, 18.0), 2),
            category=category,
            benchmark=benchmark,
            manager="Mock Asset",
            fee_rate=round(rng.uniform(0.15, 1.2), 2),
            style_exposure=["红利", "低波"] if "红利" in name else ["成长", "行业轮动"],
        )

    async def get_hot_funds(self, market: str | None = None, limit: int = 5) -> list[FundSnapshot]:
        return [await self.get_fund(code, market=market) for code in list(MOCK_FUNDS.keys())[:limit]]

    async def get_news(self, symbol: str | None = None, topic: str | None = None, limit: int = 5) -> list[MarketEvent]:
        anchor = symbol or topic or "市场"
        events: list[MarketEvent] = []
        for index in range(limit):
            events.append(
                MarketEvent(
                    title=f"{anchor} 相关事件 {index + 1}",
                    source="MockWire",
                    publish_time=self._ts(),
                    related_symbols=[symbol] if symbol else [],
                    event_type="news" if index % 2 == 0 else "announcement",
                    summary=f"{anchor} 的近期表现受政策、业绩预期和资金活跃度共同影响，需结合风险因素一起看。",
                )
            )
        return events

    async def get_technical_snapshot(self, symbol: str, market: str | None = None) -> TechnicalSnapshot:
        rng = self._rng(f"technical:{symbol}")
        rsi = round(rng.uniform(32, 72), 2)
        return TechnicalSnapshot(
            symbol=symbol,
            timestamp=self._ts(),
            ma5=round(rng.uniform(18, 320), 2),
            ma10=round(rng.uniform(18, 320), 2),
            ma20=round(rng.uniform(18, 320), 2),
            rsi14=rsi,
            macd_diff=round(rng.uniform(-2, 2), 3),
            macd_dea=round(rng.uniform(-2, 2), 3),
            macd_hist=round(rng.uniform(-1, 1), 3),
            momentum_label="strong" if rsi >= 60 else "neutral" if rsi >= 45 else "weak",
        )

    async def screen_stocks(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        lowered = query.lower()
        if "红利" in query or "股息" in query:
            picks = ["600900", "600036", "601318"]
        elif "新能源" in query:
            picks = ["300750", "002594"]
        elif "白酒" in query or "消费" in lowered:
            picks = ["600519", "000858"]
        elif "半导体" in query:
            picks = ["688981"]
        else:
            picks = list(MOCK_STOCK_UNIVERSE.keys())
        return picks[:limit]

    async def screen_funds(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        if "红利" in query:
            picks = ["510880"]
        elif "稳健" in query or "低波" in query:
            picks = ["510300", "510880"]
        else:
            picks = list(MOCK_FUNDS.keys())
        return picks[:limit]

    async def get_hot_sectors(self, market: str | None = None, limit: int = 6) -> list[SectorSnapshot]:
        seeds = [
            ("红利", "600900", "长江电力"),
            ("半导体", "688981", "中芯国际"),
            ("新能源", "300750", "宁德时代"),
            ("银行", "600036", "招商银行"),
            ("白酒", "600519", "贵州茅台"),
            ("保险", "601318", "中国平安"),
        ]
        result: list[SectorSnapshot] = []
        for sector, leader_symbol, leader_name in seeds[:limit]:
            rng = self._rng(f"sector:{sector}")
            result.append(
                SectorSnapshot(
                    sector=sector,
                    timestamp=self._ts(),
                    change_percent=round(rng.uniform(-2.0, 3.5), 2),
                    leader_symbol=leader_symbol,
                    leader_name=leader_name,
                    turnover=round(rng.uniform(5_000_000_000, 120_000_000_000), 2),
                    heat_score=round(rng.uniform(40, 96), 1),
                    catalysts=["成交放量", "政策预期改善"] if sector != "红利" else ["防御偏好回升", "股息策略关注度提升"],
                )
            )
        return result
