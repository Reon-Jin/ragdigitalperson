from __future__ import annotations

import re

from app.schemas_v2 import ConversationContextHint, HybridCopilotRequest, V2RouteDecision
from app.services.stock_resolver import StockResolver


class TaskRouter:
    _GREETING_TERMS = ("你好", "您好", "hi", "hello", "在吗", "在不在")
    _QUOTE_TERMS = ("价格", "股价", "行情", "最新价", "现在多少", "涨跌幅", "成交额", "换手率", "点位")
    _RECOMMENDATION_TERMS = ("买什么", "推荐", "值得关注", "候选", "高股息", "红利", "该买哪只", "关注哪些")
    _SCREENING_TERMS = ("筛选", "筛一筛", "有哪些", "哪几只", "适合")
    _SECTOR_TERMS = ("板块", "行业", "轮动", "热点", "为什么上涨", "哪个板块更强", "为什么更强")
    _MARKET_OVERVIEW_TERMS = (
        "股市整体",
        "整体情况",
        "市场整体",
        "大盘怎么样",
        "今天大盘",
        "今天股市",
        "盘面怎么样",
        "盘面情况",
        "市场情绪",
        "两市表现",
        "指数表现",
    )
    _RAG_TERMS = ("财报", "公告", "研报", "政策", "概念", "是什么", "为什么", "怎么理解", "怎么看", "风险", "逻辑")
    _FOLLOWUP_STOCK_TERMS = (
        "这只",
        "那只",
        "它",
        "该股",
        "这票",
        "那票",
        "这个票",
        "那个票",
        "这家公司",
        "那家公司",
        "继续分析",
        "继续看",
        "再分析",
        "再看看",
        "补充一下",
    )
    _GENERIC_STOCK_FOLLOWUPS = (
        "今天怎么样",
        "现在怎么样",
        "现在如何",
        "怎么看",
        "怎么走",
        "还能拿吗",
        "还能买吗",
        "还能追吗",
        "要不要卖",
        "要不要走",
        "后面呢",
        "接下来呢",
        "继续说",
        "展开讲讲",
    )
    _MARKET_SCOPE_TERMS = ("A股", "a股", "全市场", "所有A股", "全部A股", "市场总览", "总览", "大盘", "指数")
    _SYMBOL_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)?\d{6}\b", re.IGNORECASE)
    _FUND_PATTERN = re.compile(r"\b\d{6}\b")
    _KNOWN_SECTORS = ("新能源", "半导体", "消费", "红利", "医药", "券商", "AI", "算力")

    def __init__(self, stock_resolver: StockResolver | None = None) -> None:
        self.stock_resolver = stock_resolver

    async def route(self, payload: HybridCopilotRequest) -> V2RouteDecision:
        message = payload.message.strip()
        lowered = message.lower()
        context = payload.context_hint

        if payload.task_type != "auto":
            return await self._explicit_route(payload)

        symbol, company = await self._resolve_stock_context(message)
        reuses_stock_context = self._should_reuse_stock_context(message, context)
        if reuses_stock_context:
            symbol = symbol or (context.symbol if context else None)
            company = company or (context.company if context else None)
        fund_code = self._extract_fund_code(message) or (context.fund_code if context else None)
        sector = self._extract_sector(message) or ((context.sector if context else None) if reuses_stock_context else None)

        if self._is_greeting(message, lowered):
            return V2RouteDecision(
                task_type="finance_knowledge_qa",
                reason="识别为问候或轻量闲聊",
                company=company,
                sector=sector,
                needs_market_data=False,
                needs_rag=False,
            )

        if any(term in message for term in self._MARKET_OVERVIEW_TERMS):
            return V2RouteDecision(
                task_type="sector_rotation_analysis",
                reason="识别为大盘整体或盘面总览问题",
                company=company,
                sector=sector,
                needs_market_data=True,
                needs_rag=True,
            )

        # If the user clearly mentions a single A-share stock, always resolve it
        # through the single-stock query/analysis chain before broader sector or
        # recommendation flows.
        if symbol or company:
            if any(term in message for term in self._QUOTE_TERMS):
                return V2RouteDecision(
                    task_type="realtime_quote",
                    reason="识别为单只股票实时行情查询，优先复用 A 股个股查询能力",
                    symbol=symbol,
                    company=company,
                    sector=sector,
                    needs_market_data=True,
                    needs_rag=False,
                )
            return V2RouteDecision(
                task_type="stock_analysis",
                reason="识别为单只股票咨询，优先复用 A 股个股查询能力",
                symbol=symbol,
                company=company,
                sector=sector,
                needs_market_data=True,
                needs_rag=True,
            )

        if any(term in message for term in self._SECTOR_TERMS):
            return V2RouteDecision(
                task_type="sector_rotation_analysis",
                reason="识别为板块轮动或行业热点问题",
                sector=sector,
                company=company,
                needs_market_data=True,
                needs_rag=True,
            )

        if any(term in lowered for term in ("etf", "基金")) or (fund_code and context and context.task_type in {"fund_analysis", "fund_screening"}):
            if any(term in message for term in self._SCREENING_TERMS) or any(term in message for term in ("稳健", "低波动", "震荡市")):
                return V2RouteDecision(
                    task_type="fund_screening",
                    reason="识别为基金 / ETF 筛选问题",
                    fund_code=fund_code,
                    needs_market_data=True,
                    needs_rag=False,
                )
            return V2RouteDecision(
                task_type="fund_analysis",
                reason="识别为基金 / ETF 分析问题",
                fund_code=fund_code,
                needs_market_data=True,
                needs_rag=False,
            )

        if any(term in message for term in self._RECOMMENDATION_TERMS):
            return V2RouteDecision(
                task_type="stock_recommendation_analysis",
                reason="识别为选股或候选推荐问题",
                symbol=symbol,
                company=company,
                sector=sector,
                needs_market_data=True,
                needs_rag=True,
            )

        if any(term in message for term in self._QUOTE_TERMS):
            return V2RouteDecision(
                task_type="realtime_quote",
                reason="识别为实时市场快照问题",
                symbol=symbol,
                company=company,
                needs_market_data=True,
                needs_rag=False,
            )

        if any(term in message for term in self._RAG_TERMS):
            return V2RouteDecision(
                task_type="finance_knowledge_qa",
                reason="识别为金融知识问答",
                company=company,
                sector=sector,
                needs_market_data=False,
                needs_rag=True,
            )

        return V2RouteDecision(
            task_type=context.task_type if context and context.task_type else "finance_knowledge_qa",
            reason="默认进入金融知识问答",
            symbol=symbol,
            fund_code=fund_code,
            company=company,
            sector=sector,
            needs_market_data=bool(context and context.task_type and context.task_type != "finance_knowledge_qa"),
            needs_rag=True,
        )

    async def _explicit_route(self, payload: HybridCopilotRequest) -> V2RouteDecision:
        context = payload.context_hint
        symbol, company = await self._resolve_stock_context(payload.message)
        reuses_stock_context = self._should_reuse_stock_context(payload.message, context)
        if reuses_stock_context:
            symbol = symbol or (context.symbol if context else None)
            company = company or (context.company if context else None)
        fund_code = self._extract_fund_code(payload.message) or (context.fund_code if context else None)
        sector = self._extract_sector(payload.message) or ((context.sector if context else None) if reuses_stock_context else None)
        task_type = payload.task_type if payload.task_type != "auto" else "finance_knowledge_qa"

        # If the user explicitly mentions a single A-share stock, always prefer
        # the single-stock query/analysis chain before broader recommendation flows.
        if symbol or company:
            if any(term in payload.message for term in self._QUOTE_TERMS):
                return V2RouteDecision(
                    task_type="realtime_quote",
                    reason="显式模式下识别为单只股票实时行情查询，优先复用 A 股个股查询能力",
                    symbol=symbol,
                    company=company,
                    sector=sector,
                    needs_market_data=True,
                    needs_rag=False,
                )
            return V2RouteDecision(
                task_type="stock_analysis",
                reason="显式模式下识别为单只股票咨询，优先复用 A 股个股查询能力",
                symbol=symbol,
                company=company,
                sector=sector,
                needs_market_data=True,
                needs_rag=True,
            )

        return V2RouteDecision(
            task_type=task_type,
            reason="使用用户指定任务类型",
            symbol=symbol,
            fund_code=fund_code,
            company=company,
            sector=sector,
            needs_market_data=task_type != "finance_knowledge_qa",
            needs_rag=task_type in {"stock_analysis", "stock_recommendation_analysis", "sector_rotation_analysis", "finance_knowledge_qa"},
        )

    async def _resolve_stock_context(self, message: str) -> tuple[str | None, str | None]:
        symbol = self._extract_symbol(message)
        company = None
        if self.stock_resolver is None:
            return symbol, None

        if symbol:
            resolved = await self.stock_resolver.lookup_symbol(symbol)
            return symbol, resolved.company_name if resolved else None

        resolved = await self.stock_resolver.resolve(message)
        if resolved:
            return resolved.symbol, resolved.company_name

        return None, None

    def _should_reuse_stock_context(self, message: str, context: ConversationContextHint | None) -> bool:
        if context is None or not (context.symbol or context.company):
            return False

        compact = message.strip()
        lowered = compact.lower()

        if any(term in compact for term in self._FOLLOWUP_STOCK_TERMS):
            return True
        if compact in self._GENERIC_STOCK_FOLLOWUPS:
            return True
        if any(term in compact for term in self._MARKET_SCOPE_TERMS):
            return False
        if any(term in compact for term in self._RECOMMENDATION_TERMS):
            return False
        if any(term in compact for term in self._SCREENING_TERMS):
            return False
        if any(term in compact for term in self._SECTOR_TERMS):
            return False
        if any(term in compact for term in self._KNOWN_SECTORS):
            return False
        if "基金" in compact or "etf" in lowered:
            return False
        return False

    def _is_greeting(self, message: str, lowered: str) -> bool:
        compact = message.strip()
        if len(compact) > 12:
            return False
        return any(term in compact or term in lowered for term in self._GREETING_TERMS)

    def _extract_symbol(self, message: str) -> str | None:
        match = self._SYMBOL_PATTERN.search(message)
        if not match:
            return None
        return match.group(0).upper().replace("SH", "").replace("SZ", "").replace("BJ", "")

    def _extract_fund_code(self, message: str) -> str | None:
        if "基金" not in message and "ETF" not in message and "etf" not in message:
            return None
        match = self._FUND_PATTERN.search(message)
        return match.group(0) if match else None

    def _extract_sector(self, message: str) -> str | None:
        return next((item for item in self._KNOWN_SECTORS if item in message), None)
