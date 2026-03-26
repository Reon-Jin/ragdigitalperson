from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.market_data.providers.registry import MarketDataProviderRegistry


@dataclass(slots=True)
class ResolvedStock:
    symbol: str
    company_name: str
    aliases: tuple[str, ...] = ()


class StockResolver:
    _SYMBOL_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)?(\d{6})\b", re.IGNORECASE)
    _SEARCH_API_URL = "https://searchapi.eastmoney.com/api/suggest/get"
    _JSON_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")
    _MOJIBAKE_MARKERS = ("涓", "鍙", "鑲", "甯", "鏉", "璇", "鍏", "绗", "妯", "娣", "绾", "鍦", "閲", "闂", "锛", "锟")
    _UNIVERSE_PAGE_SIZE = 200
    _UNIVERSE_MAX_PAGES = 60
    _NON_COMPANY_PROBES = (
        "高股息",
        "红利",
        "稳健",
        "低波",
        "板块",
        "行业",
        "基金",
        "etf",
        "a股",
        "市场",
        "大盘",
        "指数",
        "热点",
        "新闻",
        "催化",
        "推荐",
        "筛选",
        "候选",
        "龙头",
        "概念",
        "主题",
    )
    _GENERIC_TERMS = (
        "分析",
        "看看",
        "咨询",
        "请问",
        "帮我",
        "一下",
        "股票",
        "个股",
        "公司",
        "代码",
        "行情",
        "走势",
        "情况",
        "表现",
        "如何",
        "怎么样",
        "现在",
        "当前",
        "目前",
        "自动",
        "这个",
        "那个",
        "这只",
        "那只",
        "一只",
        "的",
    )
    _COMPANY_SUFFIXES = (
        "股份有限公司",
        "集团股份有限公司",
        "集团有限公司",
        "有限公司",
        "股份公司",
        "集团股份",
        "控股股份",
        "控股",
        "股份",
        "集团",
        "公司",
    )
    _UNIVERSE_URLS = (
        "https://7.push2.eastmoney.com/api/qt/clist/get",
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    )
    _UNIVERSE_REQUESTS = (
        {
            "pn": 1,
            "pz": _UNIVERSE_PAGE_SIZE,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81",
            "fields": "f12,f14",
        },
        {
            "pn": 1,
            "pz": _UNIVERSE_PAGE_SIZE,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80",
            "fields": "f12,f14",
        },
        {
            "pn": 1,
            "pz": _UNIVERSE_PAGE_SIZE,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:1+t:2,m:1+t:23,m:0+t:81",
            "fields": "f12,f14",
        },
    )
    _FALLBACK_UNIVERSE = {
        "600028": ("中国石化", ("中石化", "中国石油化工", "中国石油化工股份有限公司")),
        "601857": ("中国石油", ("中石油", "中国石油天然气", "中国石油天然气股份有限公司")),
        "601398": ("工商银行", ("工行", "中国工商银行", "中国工商银行股份有限公司")),
        "600036": ("招商银行", ("招行", "招商银行股份有限公司")),
        "601318": ("中国平安", ("平安", "中国平安保险", "中国平安保险股份有限公司")),
        "600519": ("贵州茅台", ("茅台", "贵州茅台酒", "贵州茅台酒股份有限公司")),
        "000858": ("五粮液", ("宜宾五粮液", "五粮液股份有限公司")),
        "300750": ("宁德时代", ("宁王", "宁德时代新能源", "宁德时代新能源科技股份有限公司")),
        "002594": ("比亚迪", ("比亚迪股份", "比亚迪股份有限公司")),
        "688981": ("中芯国际", ("中芯", "中芯国际集成电路制造有限公司")),
        "600900": ("长江电力", ("中国长江电力", "中国长江电力股份有限公司")),
        "000333": ("美的集团", ("美的", "美的集团股份有限公司")),
        "601012": ("隆基绿能", ("隆基", "隆基绿能科技股份有限公司")),
        "300059": ("东方财富", ("东财", "东方财富信息股份有限公司")),
        "601899": ("紫金矿业", ("紫金", "紫金矿业集团股份有限公司")),
        "601088": ("中国神华", ("神华", "中国神华能源股份有限公司")),
        "600030": ("中信证券", ("中信", "中信证券股份有限公司")),
        "601166": ("兴业银行", ("兴业", "兴业银行股份有限公司")),
        "601288": ("农业银行", ("农行", "中国农业银行", "中国农业银行股份有限公司")),
        "600941": ("中国移动", ("中移动", "中国移动有限公司")),
    }

    def __init__(self, settings: Settings, market_registry: MarketDataProviderRegistry | None = None) -> None:
        self.settings = settings
        self.market_registry = market_registry
        self.cache_path = self.settings.data_dir / "stock_universe_cn.json"
        self._lock = asyncio.Lock()
        self._loaded_at: datetime | None = None
        self._records: list[ResolvedStock] = []
        self._by_symbol: dict[str, ResolvedStock] = {}
        self._records_source = "empty"

    async def resolve(self, message: str) -> ResolvedStock | None:
        symbol = self.extract_symbol(message)
        if symbol:
            return await self.lookup_symbol(symbol)

        probes = self._extract_company_probes(message)
        if not probes:
            return None

        search_match = await self._resolve_from_search_api(message, probes)
        if search_match:
            self._remember_record(search_match)
            return search_match

        remote_match = await self._resolve_from_remote_universe(message, probes)
        if remote_match:
            self._remember_record(remote_match)
            return remote_match

        records = await self._load_records()
        best = self._find_best_record(message, probes, records)
        if best:
            return best

        if self._records_source != "remote":
            refreshed = self._dedupe_records([*await self._fetch_remote_records(), *await self._fetch_akshare_records()])
            if refreshed:
                self._write_cache(refreshed)
                self._set_records(refreshed, source="remote")
                best = self._find_best_record(message, probes, self._records)
                if best:
                    return best

        akshare_match = await self._resolve_from_akshare_spot(probes)
        if akshare_match:
            self._remember_record(akshare_match)
            return akshare_match

        return None

    async def lookup_symbol(self, symbol: str) -> ResolvedStock | None:
        normalized = self._normalize_symbol(symbol)
        records = await self._load_records()
        if normalized in self._by_symbol:
            return self._by_symbol[normalized]
        return next((item for item in records if item.symbol == normalized), None)

    def extract_symbol(self, message: str) -> str | None:
        match = self._SYMBOL_PATTERN.search(message or "")
        return self._normalize_symbol(match.group(1)) if match else None

    async def _load_records(self) -> list[ResolvedStock]:
        if self._records and self._loaded_at and datetime.now(timezone.utc) - self._loaded_at < timedelta(hours=12):
            return self._records

        async with self._lock:
            if self._records and self._loaded_at and datetime.now(timezone.utc) - self._loaded_at < timedelta(hours=12):
                return self._records

            fresh_cache = self._read_cache(max_age_hours=24)
            if self._records_complete(fresh_cache):
                self._set_records(fresh_cache, source="cache")
                return self._records

            fetched = await self._fetch_remote_records()
            if not self._records_complete(fetched):
                fetched = self._dedupe_records([*fresh_cache, *fetched, *await self._fetch_akshare_records()])
            if fetched:
                self._write_cache(fetched)
                self._set_records(fetched, source="remote")
                return self._records

            stale_cache = self._read_cache(max_age_hours=None)
            if stale_cache:
                if not self._records_complete(stale_cache):
                    stale_cache = self._dedupe_records([*stale_cache, *await self._fetch_akshare_records()])
                self._set_records(stale_cache, source="stale_cache")
                return self._records

            fallback = self._fallback_records()
            self._set_records(fallback, source="fallback")
            return self._records

    def _set_records(self, records: list[ResolvedStock], *, source: str) -> None:
        merged = self._dedupe_records([*records, *self._fallback_records()])
        self._records = merged
        self._by_symbol = {item.symbol: item for item in merged}
        self._loaded_at = datetime.now(timezone.utc)
        self._records_source = source

    def _remember_record(self, record: ResolvedStock) -> None:
        merged = self._dedupe_records([*self._records, record])
        self._records = merged
        self._by_symbol = {item.symbol: item for item in merged}
        self._loaded_at = datetime.now(timezone.utc)

    def _read_cache(self, max_age_hours: int | None) -> list[ResolvedStock]:
        if not self.cache_path.exists():
            return []
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        updated_at = payload.get("updated_at")
        if updated_at and max_age_hours is not None:
            try:
                parsed = datetime.fromisoformat(updated_at)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - parsed > timedelta(hours=max_age_hours):
                    return []
            except ValueError:
                return []

        records: list[ResolvedStock] = []
        for item in payload.get("items", []):
            symbol = self._normalize_symbol(item.get("symbol"))
            company_name = self._repair_mojibake_text(item.get("company_name"))
            if not symbol or not company_name:
                continue
            aliases = tuple(
                alias
                for alias in (
                    self._repair_mojibake_text(raw_alias)
                    for raw_alias in item.get("aliases", [])
                )
                if alias
            )
            records.append(ResolvedStock(symbol=symbol, company_name=company_name, aliases=aliases))
        if self._dataset_looks_mojibake(records):
            return []
        return records

    def _write_cache(self, records: list[ResolvedStock]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {"symbol": item.symbol, "company_name": item.company_name, "aliases": list(item.aliases)}
                for item in self._dedupe_records(records)
            ],
        }
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _fetch_remote_records(self) -> list[ResolvedStock]:
        headers = {
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                merged: list[ResolvedStock] = []
                for url in self._UNIVERSE_URLS:
                    for params in self._UNIVERSE_REQUESTS:
                        merged.extend(await self._fetch_remote_records_for_market(client, url, params))
                    if len({item.symbol for item in merged}) >= 3000:
                        break
        except Exception:
            return []
        return self._dedupe_records(merged)

    async def _fetch_remote_records_for_market(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
    ) -> list[ResolvedStock]:
        merged: list[ResolvedStock] = []
        seen_page_signatures: set[tuple[str, ...]] = set()
        page_size = int(params.get("pz", self._UNIVERSE_PAGE_SIZE) or self._UNIVERSE_PAGE_SIZE)

        for page in range(1, self._UNIVERSE_MAX_PAGES + 1):
            current_params = dict(params)
            current_params["pn"] = page
            current_params["pz"] = page_size
            try:
                response = await client.get(url, params=current_params)
                response.raise_for_status()
                payload = self._decode_payload(response.content)
            except Exception:
                break

            records = self._records_from_payload(payload)
            if not records:
                break

            signature = tuple(item.symbol for item in records[:10])
            if signature in seen_page_signatures:
                break
            seen_page_signatures.add(signature)
            merged.extend(records)

            if len(records) < page_size:
                break

        return merged

    async def _resolve_from_search_api(self, raw_message: str, probes: list[str]) -> ResolvedStock | None:
        headers = {
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
        normalized_message = self._normalize_text(raw_message)
        try:
            async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
                best: tuple[int, ResolvedStock] | None = None
                for probe in self._candidate_company_probes(probes):
                    try:
                        response = await client.get(
                            self._SEARCH_API_URL,
                            params={"input": probe, "type": 14},
                        )
                        response.raise_for_status()
                        payload = response.json()
                    except Exception:
                        continue

                    items = payload.get("QuotationCodeTable", {}).get("Data") or []
                    for item in items:
                        symbol = self._normalize_symbol(
                            item.get("Code") or item.get("SecurityCode") or item.get("InnerCode")
                        )
                        company_name = self._repair_mojibake_text(
                            item.get("Name") or item.get("ShortName") or item.get("SecurityName")
                        )
                        if not symbol or not company_name:
                            quote_id = str(item.get("QuoteID") or "").strip()
                            if "." in quote_id:
                                symbol = self._normalize_symbol(quote_id.split(".", 1)[1])
                        if not symbol or not company_name:
                            continue
                        if not re.fullmatch(r"\d{6}", symbol):
                            continue
                        if not symbol.startswith(("0", "2", "3", "4", "6", "8", "9")):
                            continue
                        record = ResolvedStock(
                            symbol=symbol,
                            company_name=company_name,
                            aliases=tuple(self._aliases_for_name(company_name)),
                        )
                        score = self._score_record(raw_message, normalized_message, probes, record)
                        if score <= 0:
                            continue
                        if best is None or score > best[0]:
                            best = (score, record)
                return best[1] if best else None
        except Exception:
            return None

    async def _fetch_akshare_records(self) -> list[ResolvedStock]:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            return []
        try:
            frame = await asyncio.to_thread(ak.stock_zh_a_spot_em)
        except Exception:
            return []

        records: list[ResolvedStock] = []
        for row in frame.to_dict("records"):
            symbol = self._normalize_symbol(
                row.get("代码") or row.get("证券代码") or row.get("股票代码") or row.get("symbol")
            )
            company_name = self._repair_mojibake_text(
                row.get("名称") or row.get("证券简称") or row.get("股票简称") or row.get("name")
            )
            if not symbol or not company_name:
                continue
            aliases = tuple(self._aliases_for_name(company_name))
            records.append(ResolvedStock(symbol=symbol, company_name=company_name, aliases=aliases))
        return self._dedupe_records(records)

    async def _resolve_from_remote_universe(self, raw_message: str, probes: list[str]) -> ResolvedStock | None:
        headers = {
            "Referer": "https://quote.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
                best: tuple[int, ResolvedStock] | None = None
                for url in self._UNIVERSE_URLS:
                    for params in self._UNIVERSE_REQUESTS:
                        page_best = await self._resolve_from_remote_market_pages(client, url, params, raw_message, probes)
                        if page_best is not None and (best is None or page_best[0] > best[0]):
                            best = page_best
                            if best[0] >= 1200:
                                return best[1]
                    if best is not None:
                        return best[1]
        except Exception:
            return None
        return None

    async def _resolve_from_remote_market_pages(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        raw_message: str,
        probes: list[str],
    ) -> tuple[int, ResolvedStock] | None:
        best: tuple[int, ResolvedStock] | None = None
        seen_page_signatures: set[tuple[str, ...]] = set()
        page_size = int(params.get("pz", self._UNIVERSE_PAGE_SIZE) or self._UNIVERSE_PAGE_SIZE)
        normalized_message = self._normalize_text(raw_message)

        for page in range(1, self._UNIVERSE_MAX_PAGES + 1):
            current_params = dict(params)
            current_params["pn"] = page
            current_params["pz"] = page_size
            try:
                response = await client.get(url, params=current_params)
                response.raise_for_status()
                payload = self._decode_payload(response.content)
            except Exception:
                break

            records = self._records_from_payload(payload)
            if not records:
                break

            signature = tuple(item.symbol for item in records[:10])
            if signature in seen_page_signatures:
                break
            seen_page_signatures.add(signature)

            for record in records:
                score = self._score_record(raw_message, normalized_message, probes, record)
                if score <= 0:
                    continue
                if best is None or score > best[0]:
                    best = (score, record)

            if best is not None and best[0] >= 1200:
                return best
            if len(records) < page_size:
                break

        return best

    async def _resolve_from_akshare_spot(self, probes: list[str]) -> ResolvedStock | None:
        try:
            import akshare as ak  # type: ignore
        except Exception:
            return None

        try:
            frame = await asyncio.to_thread(ak.stock_zh_a_spot_em)
        except Exception:
            return None

        if frame is None or getattr(frame, "empty", True):
            return None

        best: tuple[int, ResolvedStock] | None = None
        for row in frame.to_dict("records"):
            symbol = self._normalize_symbol(
                row.get("代码") or row.get("证券代码") or row.get("股票代码") or row.get("symbol")
            )
            company_name = self._repair_mojibake_text(
                row.get("名称") or row.get("证券简称") or row.get("股票简称") or row.get("name")
            )
            if not symbol or not company_name:
                continue
            record = ResolvedStock(
                symbol=symbol,
                company_name=company_name,
                aliases=tuple(self._aliases_for_name(company_name)),
            )
            normalized_name = self._normalize_text(company_name)
            score = 0
            for probe in probes:
                normalized_probe = self._normalize_text(probe)
                if not normalized_probe:
                    continue
                if normalized_name == normalized_probe:
                    score = max(score, 1400 + len(normalized_probe))
                elif normalized_probe in normalized_name:
                    score = max(score, 1200 + len(normalized_probe))
                elif normalized_name in normalized_probe:
                    score = max(score, 1000 + len(normalized_name))
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, record)

        return best[1] if best else None

    def _records_from_payload(self, payload: dict) -> list[ResolvedStock]:
        diff = payload.get("data", {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())

        records: list[ResolvedStock] = []
        for item in diff:
            symbol = self._normalize_symbol(item.get("f12"))
            company_name = str(item.get("f14") or "").strip()
            if not symbol or not company_name:
                continue
            aliases = tuple(self._aliases_for_name(company_name))
            records.append(ResolvedStock(symbol=symbol, company_name=company_name, aliases=aliases))
        return records

    def _decode_payload(self, raw: bytes) -> dict:
        best_payload: dict | None = None
        best_score: tuple[int, int] | None = None
        for encoding in self._JSON_ENCODINGS:
            try:
                payload = json.loads(raw.decode(encoding))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            score = self._payload_quality(payload)
            if best_score is None or score > best_score:
                best_payload = payload
                best_score = score
        if best_payload is None:
            raise ValueError("Unable to decode stock universe payload.")
        return best_payload

    def _payload_quality(self, payload: dict) -> tuple[int, int]:
        diff = payload.get("data", {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        total = 0
        suspicious = 0
        for item in diff:
            name = str(item.get("f14") or "").strip()
            if not name:
                continue
            total += 1
            if self._looks_mojibake(name):
                suspicious += 1
        return total - suspicious, total

    def _fallback_records(self) -> list[ResolvedStock]:
        return [
            ResolvedStock(symbol=symbol, company_name=company_name, aliases=tuple(dict.fromkeys(self._aliases_for_name(company_name) + list(extra_aliases))))
            for symbol, (company_name, extra_aliases) in self._FALLBACK_UNIVERSE.items()
        ]

    def _dedupe_records(self, records: list[ResolvedStock]) -> list[ResolvedStock]:
        deduped: dict[str, ResolvedStock] = {}
        for item in records:
            symbol = self._normalize_symbol(item.symbol)
            company_name = str(item.company_name or "").strip()
            if not symbol or not company_name:
                continue
            aliases = tuple(dict.fromkeys(alias for alias in item.aliases if alias))
            current = deduped.get(symbol)
            if current is None:
                deduped[symbol] = ResolvedStock(symbol=symbol, company_name=company_name, aliases=aliases)
                continue
            merged_aliases = tuple(dict.fromkeys([*current.aliases, *aliases]))
            preferred_name = current.company_name if len(current.company_name) >= len(company_name) else company_name
            deduped[symbol] = ResolvedStock(symbol=symbol, company_name=preferred_name, aliases=merged_aliases)
        return list(deduped.values())

    def _find_best_record(self, raw_message: str, probes: list[str], records: list[ResolvedStock]) -> ResolvedStock | None:
        best: tuple[int, ResolvedStock] | None = None
        normalized_message = self._normalize_text(raw_message)
        for record in records:
            score = self._score_record(raw_message, normalized_message, probes, record)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, record)
        return best[1] if best else None

    def _score_record(self, raw_message: str, normalized_message: str, probes: list[str], record: ResolvedStock) -> int:
        score = 0
        candidates = (record.company_name, *record.aliases)
        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text:
                continue
            normalized_candidate = self._normalize_text(text)
            if text in raw_message:
                score = max(score, 1200 + len(text))
            if normalized_candidate and normalized_candidate in normalized_message:
                score = max(score, 920 + len(normalized_candidate))
            for probe in probes:
                if not probe:
                    continue
                if normalized_candidate and normalized_candidate == probe:
                    score = max(score, 1100 + len(normalized_candidate))
                if normalized_candidate and probe in normalized_candidate:
                    score = max(score, 1000 + len(probe))
                if normalized_candidate and normalized_candidate in probe:
                    score = max(score, 880 + len(normalized_candidate))
                if len(probe) >= 2 and normalized_candidate.startswith(probe):
                    score = max(score, 860 + len(probe))
        return score

    def _aliases_for_name(self, company_name: str) -> list[str]:
        aliases = [company_name.strip()]
        simplified = company_name.strip()
        for suffix in self._COMPANY_SUFFIXES:
            if simplified.endswith(suffix):
                simplified = simplified[: -len(suffix)].strip()
                break
        if simplified and simplified not in aliases and len(simplified) >= 2:
            aliases.append(simplified)
        return aliases

    def _normalize_symbol(self, symbol: str | None) -> str:
        return str(symbol or "").upper().replace("SH", "").replace("SZ", "").replace("BJ", "").strip()

    def _extract_company_probes(self, text: str) -> list[str]:
        raw = str(text or "").strip()
        normalized = self._normalize_text(raw)
        probes: list[str] = []
        if normalized:
            probes.append(normalized)
        matches = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,24}", raw)
        for item in matches:
            cleaned = self._normalize_text(item)
            if cleaned and cleaned not in probes:
                probes.append(cleaned)
        # Keep shorter Chinese-name probes as fallback for inputs like
        # "我想看看宁德时代现在怎么样".
        for item in list(probes):
            if len(item) > 4:
                for size in range(2, min(8, len(item)) + 1):
                    for start in range(0, len(item) - size + 1):
                        token = item[start:start + size]
                        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", token) and token not in probes:
                            probes.append(token)
        return probes[:24]

    def _normalize_text(self, text: str) -> str:
        normalized = str(text or "")
        for term in self._GENERIC_TERMS:
            normalized = normalized.replace(term, "")
        normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", normalized)
        return normalized.lower()

    def _candidate_company_probes(self, probes: list[str]) -> list[str]:
        ranked: list[str] = []
        for probe in sorted(dict.fromkeys(probes), key=len, reverse=True):
            text = str(probe or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if text.isdigit():
                continue
            if len(text) < 2 or len(text) > 8:
                continue
            if any(term in lowered for term in self._NON_COMPANY_PROBES):
                continue
            ranked.append(text)
        return ranked

    def _looks_mojibake(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        return any(marker in value for marker in self._MOJIBAKE_MARKERS) or "�" in value or value.endswith("?")

    def _repair_mojibake_text(self, text: str | None) -> str:
        value = str(text or "").strip()
        if not value or not self._looks_mojibake(value):
            return value
        try:
            repaired = value.encode("gb18030", errors="ignore").decode("utf-8", errors="ignore").strip()
        except Exception:
            return value
        if self._text_quality(repaired) >= self._text_quality(value):
            return repaired
        return value

    def _text_quality(self, text: str) -> int:
        value = str(text or "").strip()
        if not value:
            return -999
        valid_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", value))
        suspicious = sum(value.count(marker) for marker in self._MOJIBAKE_MARKERS)
        return valid_chars * 3 - suspicious * 5 - value.count("?") * 8 - value.count("�") * 12

    def _dataset_looks_mojibake(self, records: list[ResolvedStock]) -> bool:
        if len(records) < 50:
            return False
        suspicious = sum(1 for item in records if self._looks_mojibake(item.company_name))
        return suspicious >= max(50, len(records) // 5)

    def _records_complete(self, records: list[ResolvedStock]) -> bool:
        return len({item.symbol for item in records}) >= 3000
