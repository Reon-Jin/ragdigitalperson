from __future__ import annotations

import asyncio
import re
from datetime import datetime
from time import monotonic, perf_counter
from typing import Any

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

try:  # pragma: no cover - optional dependency
    import akshare as ak
except ImportError:  # pragma: no cover - optional dependency
    ak = None


class AkShareAdapter(
    QuoteProvider,
    FundamentalsProvider,
    FundProvider,
    NewsProvider,
    TechnicalIndicatorProvider,
    ScreenerProvider,
):
    provider_name = "akshare"
    _MAIN_INDEX_CODES = ("000001", "399001", "399006", "000300")
    _A_SHARE_NEWS_KEYWORDS = (
        "A股",
        "沪指",
        "深成指",
        "创业板",
        "科创板",
        "北交所",
        "证监会",
        "央行",
        "降准",
        "降息",
        "两市",
        "沪深",
        "主力资金",
        "北向资金",
        "南向资金",
        "龙虎榜",
        "涨停",
        "跌停",
        "板块",
        "行业",
        "业绩",
        "财报",
        "预增",
        "预亏",
        "回购",
        "分红",
        "减持",
        "重组",
        "中标",
        "订单",
        "涨价",
        "半导体",
        "AI",
        "算力",
        "机器人",
        "新能源",
        "光伏",
        "储能",
        "医药",
        "券商",
        "银行",
        "白酒",
    )
    _LOW_VALUE_NEWS_KEYWORDS = ("比特币", "以太坊", "足球", "娱乐", "明星", "美股盘前", "外汇", "原油期货")
    _CHINA_NEWS_SOURCES = (
        "财联社",
        "东方财富",
        "证券时报",
        "中国证券报",
        "证券日报",
        "上海证券报",
        "上证报",
        "第一财经",
        "新华社",
        "央视",
        "中证网",
        "人民财讯",
        "澎湃",
        "界面",
        "证券之星",
        "同花顺",
        "巨潮",
        "证监会",
        "国务院",
        "央行",
        "发改委",
        "工信部",
        "财政部",
    )

    def __init__(self) -> None:
        self._frame_cache: dict[str, tuple[float, Any]] = {}

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _ensure_client(self) -> None:
        if ak is None:
            raise RuntimeError("akshare is not installed")

    async def _run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        self._ensure_client()
        return await asyncio.to_thread(func, *args, **kwargs)

    async def _cached_frame(self, key: str, ttl: int, loader: Any, *args: Any, **kwargs: Any) -> Any:
        cache_key = f"{key}:{args}:{kwargs}"
        cached = self._frame_cache.get(cache_key)
        now = monotonic()
        if cached and now - cached[0] <= ttl:
            return cached[1]
        frame = await self._run(loader, *args, **kwargs)
        self._frame_cache[cache_key] = (now, frame)
        return frame

    def _normalize_symbol(self, symbol: str) -> str:
        cleaned = symbol.strip().upper()
        for prefix in ("SH", "SZ", "BJ", "OF", "HK", "US"):
            if cleaned.startswith(prefix):
                return cleaned[len(prefix):]
        if "." in cleaned:
            return cleaned.split(".", 1)[0]
        return cleaned

    def _exchange_from_symbol(self, symbol: str) -> str:
        if symbol.startswith("6"):
            return "SSE"
        if symbol.startswith(("0", "2", "3")):
            return "SZSE"
        if symbol.startswith(("4", "8")):
            return "BSE"
        return "CN"

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace(",", "")
        if text in {"", "-", "--", "nan", "None", "null"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _to_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text in {"-", "--", "nan", "None", "null"} else text

    def _pick(self, record: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", "-", "--"):
                return value
        return None

    def _records(self, frame: Any) -> list[dict[str, Any]]:
        if frame is None or getattr(frame, "empty", True):
            return []
        return frame.to_dict("records")

    def _find_record(self, frame: Any, symbol: str, *code_keys: str) -> dict[str, Any] | None:
        target = self._normalize_symbol(symbol)
        keys = code_keys or ("代码", "基金代码", "指数代码", "证券代码", "symbol")
        for record in self._records(frame):
            for key in keys:
                value = self._pick(record, key)
                if value and self._normalize_symbol(str(value)) == target:
                    return record
        return None

    async def _get_stock_spot_frame(self) -> Any:
        return await self._cached_frame("stock_spot", 10, ak.stock_zh_a_spot_em)

    async def _get_index_spot_frame(self) -> Any:
        return await self._cached_frame("index_spot", 20, ak.stock_zh_index_spot_em)

    async def _get_etf_spot_frame(self) -> Any:
        return await self._cached_frame("etf_spot", 20, ak.fund_etf_spot_em)

    async def _get_fund_name_frame(self) -> Any:
        return await self._cached_frame("fund_name", 3600, ak.fund_name_em)

    async def _get_sector_frame(self) -> Any:
        return await self._cached_frame("sector_board", 60, ak.stock_board_industry_name_em)

    async def get_quote(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        code = self._normalize_symbol(symbol)
        record = self._find_record(await self._get_stock_spot_frame(), code)
        if record is None:
            record = self._find_record(await self._get_etf_spot_frame(), code, "代码", "基金代码")
        if record is None:
            raise RuntimeError(f"akshare quote not found for {symbol}")

        last_price = self._to_float(self._pick(record, "最新价", "收盘"))
        prev_close = self._to_float(self._pick(record, "昨收"))
        change = self._to_float(self._pick(record, "涨跌额", "涨跌"))
        change_percent = self._to_float(self._pick(record, "涨跌幅"))
        if change is None and last_price is not None and prev_close is not None:
            change = round(last_price - prev_close, 4)
        if change_percent is None and change is not None and prev_close not in (None, 0):
            change_percent = round(change / prev_close * 100, 4)

        return QuoteSnapshot(
            symbol=code,
            name=self._to_text(self._pick(record, "名称", "证券简称", "基金简称")) or code,
            market=market or "CN",
            currency="CNY",
            timestamp=self._now(),
            last_price=last_price,
            change=change,
            change_percent=change_percent,
            open=self._to_float(self._pick(record, "今开", "开盘")),
            high=self._to_float(self._pick(record, "最高")),
            low=self._to_float(self._pick(record, "最低")),
            prev_close=prev_close,
            volume=self._to_float(self._pick(record, "成交量")),
            turnover=self._to_float(self._pick(record, "成交额")),
            amplitude=self._to_float(self._pick(record, "振幅")),
            turnover_rate=self._to_float(self._pick(record, "换手率")),
        )

    async def get_history(self, symbol: str, market: str | None = None, limit: int = 60) -> list[PriceCandle]:
        code = self._normalize_symbol(symbol)
        hist_frame = await self._run(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="qfq")
        records = self._records(hist_frame)
        if not records:
            raise RuntimeError(f"akshare history not found for {symbol}")
        return [
            PriceCandle(
                timestamp=self._to_text(self._pick(record, "日期")) or self._now(),
                open=self._to_float(self._pick(record, "开盘")),
                high=self._to_float(self._pick(record, "最高")),
                low=self._to_float(self._pick(record, "最低")),
                close=self._to_float(self._pick(record, "收盘")),
                volume=self._to_float(self._pick(record, "成交量")),
                turnover=self._to_float(self._pick(record, "成交额")),
            )
            for record in records[-limit:]
        ]

    async def get_capital_flow(self, symbol: str, market: str | None = None) -> CapitalFlowSnapshot:
        code = self._normalize_symbol(symbol)
        market_flag = "sh" if code.startswith("6") else "sz"
        try:
            frame = await self._run(ak.stock_individual_fund_flow, stock=code, market=market_flag)
        except TypeError:
            frame = await self._run(ak.stock_individual_fund_flow, symbol=code, market=market_flag)
        records = self._records(frame)
        if not records:
            raise RuntimeError(f"akshare capital flow not found for {symbol}")
        latest = records[-1]
        main_net_inflow = self._to_float(self._pick(latest, "主力净流入-净额", "主力净流入", "净流入额", "主力净额"))
        main_ratio = self._to_float(self._pick(latest, "主力净流入-净占比", "主力净占比", "净占比"))
        super_large = self._to_float(self._pick(latest, "超大单净流入-净额", "超大单净流入"))
        large = self._to_float(self._pick(latest, "大单净流入-净额", "大单净流入"))
        medium = self._to_float(self._pick(latest, "中单净流入-净额", "中单净流入"))
        small = self._to_float(self._pick(latest, "小单净流入-净额", "小单净流入"))
        if (main_net_inflow or 0) > 0:
            trend_label = "inflow"
            summary = "主力资金净流入，说明短线关注度偏强。"
        elif (main_net_inflow or 0) < 0:
            trend_label = "outflow"
            summary = "主力资金净流出，说明短线筹码承压。"
        else:
            trend_label = "neutral"
            summary = "资金流向中性，需结合量价与新闻继续确认。"
        return CapitalFlowSnapshot(
            symbol=code,
            timestamp=self._to_text(self._pick(latest, "日期", "交易日")) or self._now(),
            main_net_inflow=main_net_inflow,
            main_net_inflow_ratio=main_ratio,
            super_large_net_inflow=super_large,
            large_net_inflow=large,
            medium_net_inflow=medium,
            small_net_inflow=small,
            trend_label=trend_label,
            summary=summary,
        )

    async def get_indices(self, market: str | None = None) -> list[IndexSnapshot]:
        frame = await self._get_index_spot_frame()
        result: list[IndexSnapshot] = []
        for code in self._MAIN_INDEX_CODES:
            record = self._find_record(frame, code, "代码", "指数代码")
            if record is None:
                continue
            last_price = self._to_float(self._pick(record, "最新价", "收盘")) or 0.0
            prev_close = self._to_float(self._pick(record, "昨收")) or 0.0
            change = self._to_float(self._pick(record, "涨跌额")) or round(last_price - prev_close, 4)
            change_percent = self._to_float(self._pick(record, "涨跌幅")) or (round(change / prev_close * 100, 4) if prev_close else 0.0)
            result.append(
                IndexSnapshot(
                    symbol=code,
                    name=self._to_text(self._pick(record, "名称", "指数名称")) or code,
                    market=market or "CN",
                    timestamp=self._now(),
                    last_price=last_price,
                    change=change,
                    change_percent=change_percent,
                    turnover=self._to_float(self._pick(record, "成交额")),
                )
            )
        if not result:
            raise RuntimeError("akshare index spot is empty")
        return result

    async def get_security_profile(self, symbol: str, market: str | None = None) -> SecurityProfile:
        code = self._normalize_symbol(symbol)
        quote_record = self._find_record(await self._get_stock_spot_frame(), code) or {}

        info_map: dict[str, Any] = {}
        try:
            info_frame = await self._run(ak.stock_individual_info_em, symbol=code)
            for row in self._records(info_frame):
                key = self._to_text(self._pick(row, "item"))
                if key:
                    info_map[key] = self._pick(row, "value")
        except Exception:
            info_map = {}

        finance_record: dict[str, Any] = {}
        try:
            finance_frame = await self._run(ak.stock_financial_analysis_indicator, symbol=code)
            records = self._records(finance_frame)
            if records:
                finance_record = records[0]
        except Exception:
            finance_record = {}

        company_name = self._to_text(self._pick(info_map, "股票简称", "股票名称", "名称") or self._pick(quote_record, "名称")) or code
        industry = self._to_text(self._pick(info_map, "行业", "所属行业"))
        return SecurityProfile(
            symbol=code,
            company_name=company_name,
            sector=industry or None,
            industry=industry or None,
            exchange=self._exchange_from_symbol(code),
            market_cap=self._to_float(self._pick(info_map, "总市值")),
            pe=self._to_float(self._pick(quote_record, "市盈率-动态", "市盈率")),
            pb=self._to_float(self._pick(quote_record, "市净率")),
            dividend_yield=self._to_float(self._pick(finance_record, "现金分红率", "股息率")),
            roe=self._to_float(self._pick(finance_record, "净资产收益率", "净资产收益率(%)", "ROE")),
            debt_ratio=self._to_float(self._pick(finance_record, "资产负债率", "资产负债率(%)")),
        )

    async def get_fund(self, fund_code: str, market: str | None = None) -> FundSnapshot:
        code = self._normalize_symbol(fund_code)
        etf_record = self._find_record(await self._get_etf_spot_frame(), code, "代码", "基金代码") or {}
        fund_name_record = self._find_record(await self._get_fund_name_frame(), code, "基金代码", "代码") or {}
        nav = self._to_float(self._pick(etf_record, "最新价", "单位净值"))
        daily_change = self._to_float(self._pick(etf_record, "涨跌幅"))

        recent_1w = None
        recent_1m = None
        recent_3m = None
        drawdown = None
        nav_date = datetime.now().strftime("%Y-%m-%d")
        try:
            hist_frame = await self._run(ak.fund_etf_hist_em, symbol=code, period="daily", adjust="qfq")
            records = self._records(hist_frame)
            closes = [self._to_float(item.get("收盘")) for item in records if self._to_float(item.get("收盘")) is not None]
            if closes:
                nav = closes[-1]
                nav_date = self._to_text(self._pick(records[-1], "日期")) or nav_date
                recent_1w = self._window_return(closes, 5)
                recent_1m = self._window_return(closes, 20)
                recent_3m = self._window_return(closes, 60)
                drawdown = self._max_drawdown(closes)
        except Exception:
            pass

        fund_name = self._to_text(self._pick(etf_record, "名称", "基金简称")) or self._to_text(self._pick(fund_name_record, "基金简称", "基金名称")) or code
        category = self._to_text(self._pick(fund_name_record, "基金类型", "类型", "基金类别")) or "ETF"
        benchmark = self._to_text(self._pick(fund_name_record, "跟踪标的", "业绩比较基准"))
        manager = self._to_text(self._pick(fund_name_record, "基金公司", "管理人"))
        return FundSnapshot(
            fund_code=code,
            fund_name=fund_name,
            nav=nav,
            nav_date=nav_date,
            daily_change=daily_change,
            recent_1w=recent_1w,
            recent_1m=recent_1m,
            recent_3m=recent_3m,
            drawdown=drawdown,
            category=category or None,
            benchmark=benchmark or None,
            manager=manager or None,
            fee_rate=self._to_float(self._pick(fund_name_record, "手续费", "管理费")),
            style_exposure=self._fund_style_exposure(fund_name, category, benchmark),
        )

    async def get_hot_funds(self, market: str | None = None, limit: int = 5) -> list[FundSnapshot]:
        frame = await self._get_etf_spot_frame()
        ranked = sorted(self._records(frame), key=lambda item: self._to_float(self._pick(item, "成交额")) or 0.0, reverse=True)[:limit]
        result: list[FundSnapshot] = []
        for record in ranked:
            code = self._to_text(self._pick(record, "代码", "基金代码"))
            if not code:
                continue
            result.append(
                FundSnapshot(
                    fund_code=code,
                    fund_name=self._to_text(self._pick(record, "名称", "基金简称")) or code,
                    nav=self._to_float(self._pick(record, "最新价")),
                    nav_date=datetime.now().strftime("%Y-%m-%d"),
                    daily_change=self._to_float(self._pick(record, "涨跌幅")),
                    recent_1w=None,
                    recent_1m=None,
                    recent_3m=None,
                    drawdown=None,
                    category="ETF",
                    benchmark=None,
                    manager=None,
                    fee_rate=None,
                    style_exposure=["指数跟踪"],
                )
            )
        if not result:
            raise RuntimeError("akshare hot funds is empty")
        return result

    def _extract_symbols_from_text(self, *parts: str) -> list[str]:
        joined = " ".join(str(part or "") for part in parts)
        return list(dict.fromkeys(match.group(1) for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", joined)))

    def _is_a_share_relevant(self, title: str, summary: str, topic: str | None = None) -> bool:
        body = f"{title} {summary}"
        if any(keyword in body for keyword in self._LOW_VALUE_NEWS_KEYWORDS):
            return False
        if topic and topic not in body and topic != "A股":
            return False
        if topic == "A股":
            return any(keyword in body for keyword in self._A_SHARE_NEWS_KEYWORDS)
        return True

    def _is_china_news_source(self, source: str) -> bool:
        normalized = self._to_text(source)
        if not normalized:
            return False
        return any(keyword in normalized for keyword in self._CHINA_NEWS_SOURCES)

    def _normalize_market_event(
        self,
        record: dict[str, Any],
        *,
        default_source: str,
        topic: str | None = None,
        forced_symbol: str | None = None,
    ) -> MarketEvent | None:
        title = self._to_text(self._pick(record, "标题", "资讯标题", "新闻标题", "title"))
        if not title:
            return None
        summary = self._to_text(self._pick(record, "内容", "资讯内容", "新闻内容", "摘要", "content")) or title
        source = self._to_text(self._pick(record, "来源", "文章来源", "source")) or default_source
        if not self._is_china_news_source(source):
            return None
        if not self._is_a_share_relevant(title, summary, topic=topic):
            return None
        related_symbols = [forced_symbol] if forced_symbol else self._extract_symbols_from_text(title, summary)
        publish_time = self._to_text(self._pick(record, "发布时间", "日期", "时间", "pub_time")) or self._now()
        return MarketEvent(
            title=title,
            source=source,
            publish_time=publish_time,
            related_symbols=related_symbols,
            event_type="news",
            summary=summary,
        )

    def _event_sort_key(self, event: MarketEvent) -> tuple[int, str]:
        value = str(event.publish_time or "")
        normalized = value.replace("/", "-").replace(" ", "T")
        try:
            parsed = datetime.fromisoformat(normalized)
            return (1, parsed.isoformat())
        except ValueError:
            return (0, value)

    async def get_news(self, symbol: str | None = None, topic: str | None = None, limit: int = 5) -> list[MarketEvent]:
        if symbol:
            code = self._normalize_symbol(symbol)
            try:
                frame = await self._run(ak.stock_news_em, symbol=code)
                events = [
                    item
                    for item in (
                        self._normalize_market_event(record, default_source="Eastmoney", forced_symbol=code)
                        for record in self._records(frame)[: max(limit * 3, 12)]
                    )
                    if item is not None
                ]
                if events:
                    return events
            except Exception:
                pass

        collected: list[MarketEvent] = []
        sources: list[tuple[Any, str]] = [(ak.stock_info_global_em, "Eastmoney")]
        if hasattr(ak, "stock_info_global_cls"):
            sources.insert(0, (getattr(ak, "stock_info_global_cls"), "财联社"))

        for loader, default_source in sources:
            try:
                frame = await self._run(loader)
            except Exception:
                continue
            for record in self._records(frame):
                event = self._normalize_market_event(record, default_source=default_source, topic=topic or "A股")
                if event is not None:
                    collected.append(event)
                if len(collected) >= max(limit * 6, 24):
                    break
            if len(collected) >= max(limit * 6, 24):
                break

        unique: dict[str, MarketEvent] = {}
        for event in collected:
            key = "".join(event.title.split())
            if key and key not in unique:
                unique[key] = event
        events = sorted(unique.values(), key=self._event_sort_key, reverse=True)[:limit]
        if not events:
            raise RuntimeError("akshare news is empty")
        return events

    async def get_technical_snapshot(self, symbol: str, market: str | None = None) -> TechnicalSnapshot:
        code = self._normalize_symbol(symbol)
        hist_frame = await self._run(ak.stock_zh_a_hist, symbol=code, period="daily", adjust="qfq")
        records = self._records(hist_frame)
        if not records:
            raise RuntimeError(f"akshare technical snapshot not found for {symbol}")
        closes = [self._to_float(item.get("收盘")) for item in records if self._to_float(item.get("收盘")) is not None]
        if not closes:
            raise RuntimeError(f"akshare close prices missing for {symbol}")
        import pandas as pd

        series = pd.Series(closes)
        latest_close = float(series.iloc[-1])
        ma5 = self._rolling_mean(series, 5)
        ma10 = self._rolling_mean(series, 10)
        ma20 = self._rolling_mean(series, 20)
        rsi14 = self._rsi(series, 14)
        macd_diff, macd_dea, macd_hist = self._macd(series)
        if rsi14 is not None and rsi14 >= 60 and ma20 is not None and latest_close >= ma20:
            momentum_label = "strong"
        elif rsi14 is not None and rsi14 <= 40:
            momentum_label = "weak"
        else:
            momentum_label = "neutral"
        return TechnicalSnapshot(
            symbol=code,
            timestamp=self._now(),
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            rsi14=rsi14,
            macd_diff=macd_diff,
            macd_dea=macd_dea,
            macd_hist=macd_hist,
            momentum_label=momentum_label,
        )

    async def screen_stocks(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        frame = await self._get_stock_spot_frame()
        records = self._records(frame)
        query_lower = query.lower()

        if any(token in query for token in ("新能源", "锂电", "光伏")):
            filtered = [item for item in records if any(token in self._to_text(self._pick(item, "名称")) for token in ("能", "电", "光"))]
        elif any(token in query for token in ("红利", "股息", "稳健")):
            filtered = [
                item
                for item in records
                if (self._to_float(self._pick(item, "市盈率-动态", "市盈率")) or 999.0) <= 18
                and (self._to_float(self._pick(item, "换手率")) or 0.0) <= 8
            ]
        elif any(token in query for token in ("半导体", "芯片", "算力")):
            filtered = [item for item in records if any(token in self._to_text(self._pick(item, "名称")) for token in ("芯", "微", "导体"))]
        else:
            filtered = [
                item
                for item in records
                if query in self._to_text(self._pick(item, "名称"))
                or query in self._to_text(self._pick(item, "代码"))
                or "关注" in query_lower
                or "买" in query
            ]

        ranked = sorted(filtered or records, key=lambda item: ((self._to_float(self._pick(item, "涨跌幅")) or 0.0), (self._to_float(self._pick(item, "成交额")) or 0.0)), reverse=True)
        return [self._to_text(self._pick(item, "代码")) for item in ranked if self._to_text(self._pick(item, "代码"))][:limit]

    async def screen_funds(self, query: str, market: str | None = None, limit: int = 5) -> list[str]:
        frame = await self._get_etf_spot_frame()
        records = self._records(frame)
        if any(token in query for token in ("红利", "高股息")):
            filtered = [item for item in records if "红利" in self._to_text(self._pick(item, "名称"))]
        elif any(token in query for token in ("稳健", "低波动", "震荡")):
            filtered = [
                item
                for item in records
                if abs(self._to_float(self._pick(item, "涨跌幅")) or 0.0) <= 2.0
                and (self._to_float(self._pick(item, "成交额")) or 0.0) > 0
            ]
        else:
            filtered = [item for item in records if query in self._to_text(self._pick(item, "名称")) or query in self._to_text(self._pick(item, "代码"))]
        ranked = sorted(filtered or records, key=lambda item: self._to_float(self._pick(item, "成交额")) or 0.0, reverse=True)
        return [self._to_text(self._pick(item, "代码")) for item in ranked if self._to_text(self._pick(item, "代码"))][:limit]

    async def get_hot_sectors(self, market: str | None = None, limit: int = 6) -> list[SectorSnapshot]:
        frame = await self._get_sector_frame()
        ranked = sorted(self._records(frame), key=lambda item: self._to_float(self._pick(item, "涨跌幅")) or 0.0, reverse=True)[:limit]
        result: list[SectorSnapshot] = []
        for record in ranked:
            sector = self._to_text(self._pick(record, "板块名称", "名称")) or "行业板块"
            change_percent = self._to_float(self._pick(record, "涨跌幅")) or 0.0
            rise_count = self._to_float(self._pick(record, "上涨家数")) or 0.0
            fall_count = self._to_float(self._pick(record, "下跌家数")) or 0.0
            result.append(
                SectorSnapshot(
                    sector=sector,
                    timestamp=self._now(),
                    change_percent=change_percent,
                    leader_symbol="",
                    leader_name=self._to_text(self._pick(record, "领涨股票")) or sector,
                    turnover=self._to_float(self._pick(record, "成交额")),
                    heat_score=round(max(change_percent * 12, 0) + rise_count - fall_count * 0.2, 2),
                    catalysts=self._sector_catalysts(change_percent, rise_count, fall_count),
                )
            )
        if not result:
            raise RuntimeError("akshare sector board is empty")
        return result

    async def healthcheck(self) -> ProviderHealth:
        if ak is None:
            return ProviderHealth(provider=self.provider_name, ok=False, error="akshare is not installed")
        started = perf_counter()
        try:
            await self._get_stock_spot_frame()
        except Exception as exc:
            return ProviderHealth(
                provider=self.provider_name,
                ok=False,
                latency_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )
        return ProviderHealth(provider=self.provider_name, ok=True, latency_ms=int((perf_counter() - started) * 1000))

    def _window_return(self, values: list[float], periods: int) -> float | None:
        if len(values) <= periods:
            return None
        base = values[-periods - 1]
        current = values[-1]
        if base == 0:
            return None
        return round((current - base) / base * 100, 2)

    def _max_drawdown(self, values: list[float]) -> float | None:
        if not values:
            return None
        peak = values[0]
        max_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            if peak:
                max_drawdown = min(max_drawdown, (value - peak) / peak)
        return round(abs(max_drawdown) * 100, 2)

    def _rolling_mean(self, series: Any, window: int) -> float | None:
        if len(series) < window:
            return None
        return round(float(series.tail(window).mean()), 4)

    def _rsi(self, series: Any, window: int) -> float | None:
        if len(series) <= window:
            return None
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=window).mean().iloc[-1]
        avg_loss = loss.rolling(window=window).mean().iloc[-1]
        if avg_gain is None or avg_loss is None:
            return None
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _macd(self, series: Any) -> tuple[float | None, float | None, float | None]:
        if len(series) < 26:
            return None, None, None
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        diff = ema12 - ema26
        dea = diff.ewm(span=9, adjust=False).mean()
        hist = (diff - dea) * 2
        return round(float(diff.iloc[-1]), 4), round(float(dea.iloc[-1]), 4), round(float(hist.iloc[-1]), 4)

    def _fund_style_exposure(self, name: str, category: str, benchmark: str) -> list[str]:
        raw = f"{name} {category} {benchmark}"
        tags: list[str] = []
        if "红利" in raw or "股息" in raw:
            tags.append("红利")
        if "低波" in raw or "稳健" in raw:
            tags.append("低波")
        if "创业板" in raw or "科创" in raw or "成长" in raw:
            tags.append("成长")
        if "沪深300" in raw or "宽基" in raw:
            tags.append("宽基")
        if "消费" in raw or "酒" in raw:
            tags.append("消费")
        return tags or ["指数跟踪"]

    def _sector_catalysts(self, change_percent: float, rise_count: float, fall_count: float) -> list[str]:
        catalysts: list[str] = []
        if change_percent >= 2:
            catalysts.append("板块涨幅居前，短线资金活跃度较高。")
        if rise_count > fall_count:
            catalysts.append("上涨家数占优，板块扩散度较好。")
        if not catalysts:
            catalysts.append("当前强度一般，仍需观察持续性。")
        return catalysts
