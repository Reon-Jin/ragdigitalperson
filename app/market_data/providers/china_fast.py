from __future__ import annotations

import httpx
from datetime import datetime

from app.market_data.providers.base import ProviderHealth, QuoteProvider
from app.market_data.schemas.quote import IndexSnapshot, QuoteSnapshot


class ChinaFastAdapter(QuoteProvider):
    provider_name = "chinafast"
    _BASE_URL = "https://hq.sinajs.cn/list="
    _INDEX_CODES = {
        "000001": ("sh000001", "上证指数"),
        "399001": ("sz399001", "深证成指"),
        "399006": ("sz399006", "创业板指"),
        "000300": ("sh000300", "沪深300"),
    }

    def _symbol_to_market_code(self, symbol: str) -> str:
        if symbol.startswith(("sh", "sz")):
            return symbol
        if symbol.startswith("6"):
            return f"sh{symbol}"
        return f"sz{symbol}"

    def _parse_row(self, payload: str) -> list[str]:
        _, _, remainder = payload.partition('="')
        content, _, _ = remainder.partition('";')
        return [item.strip() for item in content.split(",") if item.strip()]

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    async def _fetch(self, codes: list[str]) -> list[str]:
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }
        async with httpx.AsyncClient(timeout=3.5, headers=headers) as client:
            response = await client.get(f"{self._BASE_URL}{','.join(codes)}")
            response.raise_for_status()
            return [line for line in response.text.splitlines() if line.strip()]

    async def get_quote(self, symbol: str, market: str | None = None) -> QuoteSnapshot:
        market_code = self._symbol_to_market_code(symbol)
        rows = await self._fetch([market_code])
        if not rows:
            raise RuntimeError(f"chinafast quote not found for {symbol}")
        fields = self._parse_row(rows[0])
        if len(fields) < 10:
            raise RuntimeError(f"chinafast quote payload is invalid for {symbol}")
        name = fields[0]
        open_price = float(fields[1]) if fields[1] else None
        prev_close = float(fields[2]) if fields[2] else None
        last_price = float(fields[3]) if fields[3] else None
        high = float(fields[4]) if fields[4] else None
        low = float(fields[5]) if fields[5] else None
        volume = float(fields[8]) if fields[8] else None
        turnover = float(fields[9]) if fields[9] else None
        change = round((last_price or 0) - (prev_close or 0), 4) if last_price is not None and prev_close is not None else None
        change_percent = round(change / prev_close * 100, 4) if change is not None and prev_close not in (None, 0) else None
        amplitude = round((high - low) / prev_close * 100, 4) if high is not None and low is not None and prev_close not in (None, 0) else None
        return QuoteSnapshot(
            symbol=symbol,
            name=name or symbol,
            market=market or "CN",
            currency="CNY",
            timestamp=self._now(),
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
            turnover_rate=None,
        )

    async def get_indices(self, market: str | None = None) -> list[IndexSnapshot]:
        rows = await self._fetch([item[0] for item in self._INDEX_CODES.values()])
        result: list[IndexSnapshot] = []
        for code, row in zip(self._INDEX_CODES.keys(), rows):
            fields = self._parse_row(row)
            if len(fields) < 10:
                continue
            last_price = float(fields[3]) if fields[3] else 0.0
            prev_close = float(fields[2]) if fields[2] else 0.0
            change = round(last_price - prev_close, 4)
            change_percent = round(change / prev_close * 100, 4) if prev_close else 0.0
            result.append(
                IndexSnapshot(
                    symbol=code,
                    name=fields[0] or self._INDEX_CODES[code][1],
                    market=market or "CN",
                    timestamp=self._now(),
                    last_price=last_price,
                    change=change,
                    change_percent=change_percent,
                    turnover=float(fields[9]) if len(fields) > 9 and fields[9] else None,
                )
            )
        if not result:
            raise RuntimeError("chinafast index payload is empty")
        return result

    async def healthcheck(self) -> ProviderHealth:
        started = datetime.now()
        try:
            await self._fetch(["sh000001"])
            latency_ms = int((datetime.now() - started).total_seconds() * 1000)
            return ProviderHealth(provider=self.provider_name, ok=True, latency_ms=latency_ms)
        except Exception as exc:
            latency_ms = int((datetime.now() - started).total_seconds() * 1000)
            return ProviderHealth(provider=self.provider_name, ok=False, latency_ms=latency_ms, error=str(exc))
