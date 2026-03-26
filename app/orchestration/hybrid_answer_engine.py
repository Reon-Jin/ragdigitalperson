from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.knowledge_base.profile_store import ProfileStore
from app.market_data.service.news_curator import MarketNewsCurator
from app.market_data.service.news_service import NewsService
from app.market_data.schemas.screening import RecommendationRequest
from app.orchestration.citation_builder import CitationBuilder
from app.orchestration.task_router import TaskRouter
from app.retrieval.finance_retriever import FinanceRetriever
from app.schemas_v2 import HybridAnswerPayload, HybridCopilotRequest, UserProfile, V2RouteDecision
from app.services.agent_memory_store import AgentMemoryStore
from app.services.deepseek_client import CompatibleLLMClient
from app.ui_api.dashboard_api import DashboardAPI
from app.ui_api.fund_api import FundAPI
from app.ui_api.quote_api import QuoteAPI
from app.ui_api.recommendation_api import RecommendationAPI
from app.ui_api.stock_api import StockAPI


class HybridAnswerEngine:
    _LIVE_NEWS_TERMS = ("新闻", "热点", "事件", "催化", "最新", "刚刚", "盘后", "盘中", "快讯")

    def __init__(
        self,
        *,
        profile_store: ProfileStore,
        agent_memory_store: AgentMemoryStore,
        task_router: TaskRouter,
        dashboard_api: DashboardAPI,
        news_service: NewsService,
        news_curator: MarketNewsCurator,
        quote_api: QuoteAPI,
        stock_api: StockAPI,
        fund_api: FundAPI,
        recommendation_api: RecommendationAPI,
        finance_retriever: FinanceRetriever,
        citation_builder: CitationBuilder,
        llm_client: CompatibleLLMClient,
    ) -> None:
        self.profile_store = profile_store
        self.agent_memory_store = agent_memory_store
        self.task_router = task_router
        self.dashboard_api = dashboard_api
        self.news_service = news_service
        self.news_curator = news_curator
        self.quote_api = quote_api
        self.stock_api = stock_api
        self.fund_api = fund_api
        self.recommendation_api = recommendation_api
        self.finance_retriever = finance_retriever
        self.citation_builder = citation_builder
        self.llm_client = llm_client

    async def stream(self, payload: HybridCopilotRequest) -> AsyncIterator[dict[str, Any]]:
        profile = self.profile_store.get(payload.profile_id)
        memory = self.agent_memory_store.get(payload.user_id or payload.profile_id)
        yield {"type": "ack", "message": "正在识别问题类型"}
        yield self._avatar_cue(state="thinking", gesture="analyze", state_label="思考中", gesture_label="推演", expression="focus")

        route = await self.task_router.route(payload)
        yield {"type": "route", "route": route.model_dump()}
        yield self._route_avatar_cue(route)

        market_task = None
        rag_task = None

        if route.needs_market_data:
            yield {"type": "market_fetch_started", "message": "正在拉取实时市场数据"}
            market_task = asyncio.create_task(self._run_market_step(route, payload, profile))

        if route.needs_rag:
            yield {"type": "rag_fetch_started", "message": "正在匹配知识证据"}
            rag_task = asyncio.create_task(self._run_rag_step(route, payload))

        market_result: dict[str, Any] | None = None
        rag_result: dict[str, Any] | None = None
        citations: list[dict[str, Any]] = []
        warnings: list[str] = []

        if market_task is not None:
            try:
                market_result = await market_task
                yield {"type": "market_fetch_done", "result": market_result}
                yield self._avatar_cue(state="thinking", gesture="acknowledge", state_label="数据已到位", gesture_label="确认", duration=0.9)
            except Exception as exc:
                warnings.append(f"实时数据阶段已降级：{exc}")
                yield {"type": "market_fetch_done", "result": {}, "degraded": True}
                yield self._avatar_cue(state="warn", gesture="warn", state_label="数据降级", gesture_label="警示", expression="warn")

        if rag_task is not None:
            try:
                rag_result, citations = await rag_task
                yield {"type": "rag_fetch_done", "citations": citations}
                yield self._avatar_cue(state="thinking", gesture="acknowledge", state_label="证据匹配完成", gesture_label="确认", duration=0.9)
            except Exception as exc:
                warnings.append(f"知识证据阶段已降级：{exc}")
                yield {"type": "rag_fetch_done", "citations": [], "degraded": True}
                yield self._avatar_cue(state="warn", gesture="warn", state_label="证据降级", gesture_label="警示", expression="warn")

        initial_cards = self._build_cards(route, market_result, rag_result, citations, warnings)
        if initial_cards:
            yield {"type": "analysis_cards", "cards": initial_cards}
        if citations:
            yield {"type": "citations", "items": citations[:5]}
        yield self._avatar_cue(state="speaking", gesture="explain", state_label="讲解中", gesture_label="说明", expression="warm")

        answer_parts: list[str] = []
        try:
            async for delta in self._stream_answer(route, payload, profile, memory, market_result, rag_result, citations, warnings):
                answer_parts.append(delta)
                yield {"type": "delta", "delta": delta}
        except Exception as exc:
            warnings.append(f"大模型生成阶段已降级：{exc}")

        answer = "".join(answer_parts).strip()
        if not answer:
            answer = self._build_fallback_answer(route, profile, market_result, rag_result, citations, warnings)
            for index in range(0, len(answer), 64):
                yield {"type": "delta", "delta": answer[index:index + 64]}

        final = HybridAnswerPayload(
            route=route,
            answer=answer,
            cards=self._build_cards(route, market_result, rag_result, citations, warnings),
            citations=citations[:5],
            metadata={
                "analysis_mode": payload.analysis_mode,
                "profile": profile.model_dump(),
                "memory": memory.model_dump(),
                "warnings": warnings,
                "provider": self.llm_client.normalize_provider(payload.model_provider),
            },
        )
        yield {"type": "final", **final.model_dump()}

    def _avatar_cue(
        self,
        *,
        state: str,
        gesture: str,
        state_label: str | None = None,
        gesture_label: str | None = None,
        expression: str | None = None,
        duration: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "avatar_cue",
            "state": state,
            "gesture": gesture,
        }
        if state_label:
            payload["state_label"] = state_label
        if gesture_label:
            payload["gesture_label"] = gesture_label
        if expression:
            payload["expression"] = expression
        if duration is not None:
            payload["duration"] = duration
        return payload

    def _route_avatar_cue(self, route: V2RouteDecision) -> dict[str, Any]:
        if route.task_type == "stock_analysis":
            return self._avatar_cue(state="thinking", gesture="explain", state_label="聚焦个股", gesture_label="拆解", expression="focus")
        if route.task_type == "stock_recommendation_analysis":
            return self._avatar_cue(state="thinking", gesture="emphasize", state_label="筛选候选", gesture_label="强调", expression="focus")
        if route.task_type == "realtime_quote":
            return self._avatar_cue(state="thinking", gesture="acknowledge", state_label="读取行情", gesture_label="确认", expression="focus")
        if route.task_type == "sector_rotation_analysis":
            return self._avatar_cue(state="thinking", gesture="broadcast", state_label="扫描板块", gesture_label="轮动", expression="focus")
        if route.task_type == "finance_knowledge_qa":
            return self._avatar_cue(state="thinking", gesture="analyze", state_label="整理知识", gesture_label="归纳", expression="focus")
        return self._avatar_cue(state="thinking", gesture="acknowledge", state_label="继续分析", gesture_label="确认", expression="focus")

    async def _stream_answer(
        self,
        route: V2RouteDecision,
        payload: HybridCopilotRequest,
        profile: UserProfile,
        memory,
        market_result: dict[str, Any] | None,
        rag_result: dict[str, Any] | None,
        citations: list[dict[str, Any]],
        warnings: list[str],
    ) -> AsyncIterator[str]:
        provider = self.llm_client.normalize_provider(payload.model_provider)
        if not self.llm_client.is_configured(provider):
            return

        messages = self._build_llm_messages(
            route=route,
            payload=payload,
            profile=profile,
            memory=memory,
            market_result=market_result,
            rag_result=rag_result,
            citations=citations,
            warnings=warnings,
        )
        async for delta in self.llm_client.stream_chat(messages, provider=provider, temperature=0.25):
            if delta:
                yield delta

    async def _run_market_step(
        self,
        route: V2RouteDecision,
        payload: HybridCopilotRequest,
        profile: UserProfile,
    ) -> dict[str, Any]:
        if route.task_type == "realtime_quote" and route.symbol:
            return (await self.quote_api.get_quote(route.symbol)).model_dump()
        if route.task_type == "stock_analysis" and route.symbol:
            return (await self.stock_api.analyze(route.symbol)).model_dump()
        if route.task_type == "fund_analysis" and route.fund_code:
            return (await self.fund_api.analyze(route.fund_code)).model_dump()
        if route.task_type == "stock_recommendation_analysis":
            result = await self.recommendation_api.recommend_stocks(
                RecommendationRequest(
                    query=payload.message,
                    risk_level=profile.risk_level,
                    investment_horizon=profile.investment_horizon,
                    analysis_mode=payload.analysis_mode,
                    limit=5,
                )
            )
            return result.model_dump()
        if route.task_type == "fund_screening":
            return (
                await self.fund_api.screen(
                    payload.message,
                    risk_level=profile.risk_level,
                    limit=5,
                )
            ).model_dump()
        if route.task_type == "sector_rotation_analysis":
            overview = await self.dashboard_api.overview()
            result = overview.model_dump()
            if route.sector:
                result["focus_sector"] = next(
                    (item for item in result.get("hot_sectors", []) if route.sector in item.get("sector", "")),
                    None,
                )
            return result
        return {}

    async def _run_rag_step(
        self,
        route: V2RouteDecision,
        payload: HybridCopilotRequest,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if route.task_type == "sector_rotation_analysis":
            retrieval_task_type = "sector_analysis"
        elif route.task_type in {"stock_analysis", "stock_recommendation_analysis"}:
            retrieval_task_type = "stock_analysis"
        else:
            retrieval_task_type = "general_finance_qa"

        retrieval_task = asyncio.to_thread(
            self.finance_retriever.retrieve,
            payload.message,
            task_type=retrieval_task_type,
            user_id=payload.user_id or payload.profile_id,
            company=route.company,
            ticker=route.symbol,
            sector=route.sector,
        )
        live_news_task = None
        if self._should_attach_live_news(route, payload):
            live_news_task = asyncio.create_task(self._load_live_news(route, payload))
        retrieval = await retrieval_task
        live_news = await live_news_task if live_news_task is not None else []
        citations = [item.model_dump() for item in self.citation_builder.build(retrieval["chunks"])]
        if live_news:
            live_news_citations = [self._news_to_citation(item, index) for index, item in enumerate(live_news)]
            retrieval["live_news"] = [item.model_dump() for item in live_news]
            retrieval["evidence_summary"] = self._merge_live_news_evidence(retrieval.get("evidence_summary", {}), live_news)
            citations = [*live_news_citations, *citations]
        return retrieval, citations

    def _should_attach_live_news(self, route: V2RouteDecision, payload: HybridCopilotRequest) -> bool:
        message = payload.message or ""
        mentions_news = any(term in message for term in self._LIVE_NEWS_TERMS)
        if route.task_type == "finance_knowledge_qa":
            return mentions_news
        if route.task_type == "sector_rotation_analysis":
            return mentions_news
        # Stock detail, recommendation and quote paths already pull real-time
        # market/news data via the market-data step, so avoid duplicating the
        # same news fetch in RAG unless the user explicitly asks for hot news.
        if route.task_type in {"stock_analysis", "stock_recommendation_analysis", "realtime_quote"}:
            return False
        return mentions_news

    async def _load_live_news(self, route: V2RouteDecision, payload: HybridCopilotRequest) -> list[Any]:
        symbol = route.symbol
        topic = route.sector or ("A股" if route.task_type in {"finance_knowledge_qa", "stock_recommendation_analysis", "sector_rotation_analysis"} else None)
        try:
            items = await self.news_service.get_news(symbol=symbol, topic=topic, limit=12)
        except Exception:
            return []
        curated = self.news_curator.curate(items, limit=4, focus_symbol=symbol)
        return curated

    def _merge_live_news_evidence(self, evidence_summary: dict[str, Any], live_news: list[Any]) -> dict[str, Any]:
        merged = dict(evidence_summary or {})
        support = list(merged.get("support", []))
        drivers = list(merged.get("drivers", []))
        timeline = list(merged.get("timeline", []))
        for item in live_news[:4]:
            support.append(f"实时新闻 | {item.title} | {item.summary}")
            drivers.append(f"{item.theme or item.event_type or '热点'} | {item.title}")
            timeline.append(f"{item.publish_time} | {item.source} | {item.title}")
        merged["support"] = support[:5]
        merged["drivers"] = drivers[:5]
        merged["timeline"] = timeline[:5]
        return merged

    def _news_to_citation(self, item: Any, index: int) -> dict[str, Any]:
        return {
            "doc_id": f"live-news-{index}",
            "title": item.title,
            "section_title": f"实时热点新闻 / {item.source}",
            "preview": item.summary,
            "time_label": item.publish_time,
            "score": item.importance_score or 0.0,
            "location_label": item.theme or item.event_type or "热点",
            "stance": "support",
        }

    def _build_llm_messages(
        self,
        *,
        route: V2RouteDecision,
        payload: HybridCopilotRequest,
        profile: UserProfile,
        memory,
        market_result: dict[str, Any] | None,
        rag_result: dict[str, Any] | None,
        citations: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[dict[str, str]]:
        system_prompt = self._build_system_prompt(payload.analysis_mode, route.task_type)
        context = self._build_context_payload(route, profile, memory, market_result, rag_result, citations, warnings)
        user_prompt = (
            f"用户问题：{payload.message}\n\n"
            f"路由任务：{route.task_type}\n"
            f"路由原因：{route.reason}\n\n"
            "以下是系统已经准备好的结构化上下文，请优先使用这些内容，不要编造不存在的实时数据。\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}"
        )
        messages = [{"role": "system", "content": system_prompt}]
        for item in payload.history[-8:]:
            if item.content.strip():
                messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _build_system_prompt(self, analysis_mode: str, task_type: str) -> str:
        tone_map = {
            "summary": "回答简洁，优先给结论和关键依据。",
            "professional": "回答专业、克制、结构清晰，像金融分析终端里的研究助理。",
            "teaching": "回答兼顾解释性，适合教学和科普，但仍要保持专业。",
        }
        task_rule = (
            "如果用户只是打招呼或寒暄，直接自然回应，并给出 2 到 3 个可继续追问的金融分析方向。"
            if task_type == "finance_knowledge_qa"
            else "如果涉及行情、筛选、推荐或比较，必须结合已提供的市场数据和证据作答。"
        )
        return (
            "你是 FinAvatar 金融智能分析助理。\n"
            "回答要求：\n"
            "1. 全部使用中文。\n"
            "2. 严格基于提供的市场数据、知识证据和用户画像作答；没有的数据就明确说没有，不要编造。\n"
            "3. 如果是“买什么、关注什么、筛选什么”之类问题，只能给候选和分析，必须包含风险提示、不确定性说明，并自然说明“不构成个性化投资建议”。\n"
            "4. 不要输出“稳赚不赔”“一定涨”“立刻重仓”这类承诺。\n"
            "5. 输出尽量分段，先给核心判断，再给依据，再给风险或下一步建议。\n"
            f"6. {tone_map.get(analysis_mode, tone_map['professional'])}\n"
            f"7. {task_rule}"
        )

    def _build_context_payload(
        self,
        route: V2RouteDecision,
        profile: UserProfile,
        memory,
        market_result: dict[str, Any] | None,
        rag_result: dict[str, Any] | None,
        citations: list[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        evidence = (rag_result or {}).get("evidence_summary", {})
        return {
            "user_profile": profile.model_dump(),
            "agent_memory": memory.model_dump() if hasattr(memory, "model_dump") else memory,
            "market_result": self._trim_market_result(route, market_result or {}),
            "live_news": (rag_result or {}).get("live_news", [])[:4],
            "evidence_summary": {
                "support": evidence.get("support", [])[:3],
                "risks": evidence.get("risks", [])[:3],
                "metrics": evidence.get("metrics", [])[:4],
                "drivers": evidence.get("drivers", [])[:4],
                "timeline": evidence.get("timeline", [])[:4],
            },
            "citations": [
                {
                    "title": item.get("title"),
                    "section_title": item.get("section_title"),
                    "preview": item.get("preview"),
                    "time_label": item.get("time_label"),
                    "score": item.get("score"),
                }
                for item in citations[:4]
            ],
            "warnings": warnings[:3],
        }

    def _trim_market_result(self, route: V2RouteDecision, market_result: dict[str, Any]) -> dict[str, Any]:
        if route.task_type == "realtime_quote":
            return {"quote": market_result.get("quote", {}), "technical": market_result.get("technical", {})}
        if route.task_type == "stock_analysis":
            return {
                "quote": market_result.get("quote", {}),
                "technical": market_result.get("technical", {}),
                "profile": market_result.get("profile", {}),
                "capital_flow": market_result.get("capital_flow", {}),
                "history": market_result.get("history", [])[-20:],
                "highlights": market_result.get("highlights", [])[:4],
                "risks": market_result.get("risks", [])[:4],
                "news": market_result.get("news", [])[:3],
            }
        if route.task_type == "fund_analysis":
            return {
                "snapshot": market_result.get("snapshot", {}),
                "highlights": market_result.get("highlights", [])[:4],
                "risks": market_result.get("risks", [])[:4],
            }
        if route.task_type == "stock_recommendation_analysis":
            return {
                "market_view": market_result.get("market_view"),
                "clarification_question": market_result.get("clarification_question"),
                "clarification_options": market_result.get("clarification_options", []),
                "risk_notes": market_result.get("risk_notes", [])[:4],
                "candidates": market_result.get("candidates", [])[:5],
            }
        if route.task_type == "fund_screening":
            return {
                "disclaimer": market_result.get("disclaimer"),
                "items": market_result.get("items", [])[:5],
            }
        if route.task_type == "sector_rotation_analysis":
            return {
                "market_sentiment": market_result.get("market_sentiment", {}),
                "focus_sector": market_result.get("focus_sector"),
                "hot_sectors": market_result.get("hot_sectors", [])[:5],
                "latest_events": market_result.get("latest_events", [])[:4],
            }
        return {}

    def _build_cards(
        self,
        route: V2RouteDecision,
        market_result: dict[str, Any] | None,
        rag_result: dict[str, Any] | None,
        citations: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []

        if route.task_type == "realtime_quote" and market_result and market_result.get("quote"):
            quote = market_result["quote"]
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": f"{quote.get('name', quote.get('symbol', '标的'))} 行情快照",
                    "summary": f"最新价 {quote.get('last_price', '--')}，涨跌幅 {quote.get('change_percent', '--')}%",
                    "items": [
                        f"成交额 {self._fmt_turnover(quote.get('turnover'))}",
                        f"换手率 {self._fmt_percent(quote.get('turnover_rate'))}",
                        f"振幅 {self._fmt_percent(quote.get('amplitude'))}",
                    ],
                }
            )

        if route.task_type == "stock_analysis" and market_result:
            detail_items = self._build_stock_detail_items(market_result)
            if detail_items:
                cards.append(
                    {
                        "card_type": "security",
                        "title": "股票候选详情",
                        "summary": self._build_stock_detail_summary(market_result),
                        "items": detail_items,
                        "payload": {
                            "quote": market_result.get("quote", {}),
                            "technical": market_result.get("technical", {}),
                            "profile": market_result.get("profile", {}),
                            "capital_flow": market_result.get("capital_flow", {}),
                            "history": market_result.get("history", [])[-40:],
                            "news": market_result.get("news", [])[:3],
                        },
                    }
                )
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": "个股分析结论",
                    "summary": (market_result.get("highlights") or ["已结合实时数据和基本面快照生成结论。"])[0],
                    "items": market_result.get("highlights", [])[:4],
                }
            )
            cards.append(
                {
                    "card_type": "risk",
                    "title": "主要风险",
                    "summary": "结合行情、基本面和近期信息得出的风险提示。",
                    "items": market_result.get("risks", [])[:4] or ["暂无明确风险条目，建议继续核对公告与财报。"],
                }
            )

        if route.task_type == "stock_recommendation_analysis" and market_result:
            if market_result.get("clarification_question"):
                cards.append(
                    {
                        "card_type": "conclusion",
                        "title": "需要先补充需求",
                        "summary": market_result.get("clarification_question"),
                        "items": market_result.get("clarification_options", []),
                    }
                )
                return cards
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": "候选清单",
                    "summary": market_result.get("market_view", "以下候选基于当前快照筛选，不构成个性化投资建议。"),
                    "items": [
                        f"{item.get('name', '--')} | {item.get('attention_reason', '--')} | {item.get('capital_flow', '--')}"
                        for item in market_result.get("candidates", [])[:5]
                    ],
                }
            )
            cards.append(
                {
                    "card_type": "risk",
                    "title": "边界与风险",
                    "summary": market_result.get("disclaimer", "以下仅基于当前公开数据和系统快照。"),
                    "items": market_result.get("risk_notes", [])[:4] or ["市场风格变化、基本面兑现和情绪回落都可能影响结论。"],
                }
            )

        if route.task_type == "fund_analysis" and market_result:
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": "基金 / ETF 概览",
                    "summary": (market_result.get("highlights") or ["已生成基金 / ETF 快照分析。"])[0],
                    "items": market_result.get("highlights", [])[:4],
                }
            )
            cards.append(
                {
                    "card_type": "risk",
                    "title": "风险提示",
                    "summary": "基金波动、回撤和风格漂移需要结合周期判断。",
                    "items": market_result.get("risks", [])[:4] or ["建议继续结合波动、回撤和持仓风格观察。"],
                }
            )

        if route.task_type == "fund_screening" and market_result:
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": "基金 / ETF 筛选结果",
                    "summary": market_result.get("disclaimer", "以下结果基于当前筛选条件。"),
                    "items": [
                        f"{item.get('fund_name', '--')} | {item.get('reason', '--')} | {item.get('style_fit', '--')}"
                        for item in market_result.get("items", [])[:5]
                    ],
                }
            )

        if route.task_type == "sector_rotation_analysis" and market_result:
            focus = market_result.get("focus_sector")
            summary = (
                f"{focus.get('sector', '--')} 当前涨跌幅 {focus.get('change_percent', '--')}%，热度 {focus.get('heat_score', '--')}"
                if isinstance(focus, dict)
                else market_result.get("market_sentiment", {}).get("summary", "当前以市场总览为主")
            )
            cards.append(
                {
                    "card_type": "conclusion",
                    "title": "板块轮动",
                    "summary": summary,
                    "items": [
                        f"{item.get('sector', '--')} | 涨跌幅 {item.get('change_percent', '--')}% | 龙头 {item.get('leader_name', '--')}"
                        for item in market_result.get("hot_sectors", [])[:6]
                    ],
                }
            )

        evidence_summary = (rag_result or {}).get("evidence_summary", {})
        evidence_items = evidence_summary.get("support", [])[:3] + evidence_summary.get("risks", [])[:2]
        if evidence_items:
            cards.append(
                {
                    "card_type": "sources",
                    "title": "知识证据",
                    "summary": "本次回答同时参考知识库中的支持证据与风险证据。",
                    "items": evidence_items,
                }
            )

        live_news = (rag_result or {}).get("live_news", [])[:3]
        if live_news:
            cards.append(
                {
                    "card_type": "timeline",
                    "title": "实时热点新闻",
                    "summary": "以下热点已作为动态证据并入本次回答上下文。",
                    "items": [f"{item.get('publish_time', '--')} | {item.get('title', '--')}" for item in live_news],
                }
            )

        if citations:
            cards.append(
                {
                    "card_type": "timeline",
                    "title": "来源清单",
                    "summary": "以下是本次回答引用的核心材料。",
                    "items": [f"{item.get('title', '--')} | {item.get('section_title') or '未分节'}" for item in citations[:4]],
                }
            )

        if warnings:
            cards.append(
                {
                    "card_type": "risk",
                    "title": "系统提示",
                    "summary": "本次回答部分链路已降级，但仍输出了可用结果。",
                    "items": warnings[:3],
                }
            )

        return cards

    def _build_fallback_answer(
        self,
        route: V2RouteDecision,
        profile: UserProfile,
        market_result: dict[str, Any] | None,
        rag_result: dict[str, Any] | None,
        citations: list[dict[str, Any]],
        warnings: list[str],
    ) -> str:
        evidence_summary = (rag_result or {}).get("evidence_summary", {})
        support = evidence_summary.get("support", [])[:3]
        risks = evidence_summary.get("risks", [])[:2]
        warning_text = f"\n\n系统提示：{'；'.join(warnings[:2])}。" if warnings else ""

        if route.task_type == "finance_knowledge_qa" and self._is_greeting_like(route):
            return (
                "你好，我是 FinAvatar。\n\n"
                "我可以直接帮你看实时行情、个股 / ETF / 基金分析、板块轮动、财报与风险提示。\n"
                "你可以继续这样问我：\n"
                "- 现在贵州茅台价格是多少？\n"
                "- 当前有哪些高股息标的值得关注？\n"
                "- 最近新能源板块为什么上涨？"
            )

        if route.task_type == "realtime_quote" and market_result and market_result.get("quote"):
            quote = market_result["quote"]
            return (
                f"{quote.get('name', quote.get('symbol', '该标的'))}当前最新价为 {quote.get('last_price', '--')}，"
                f"涨跌幅 {quote.get('change_percent', '--')}%，成交额 {self._fmt_turnover(quote.get('turnover'))}，"
                f"换手率 {self._fmt_percent(quote.get('turnover_rate'))}。"
                f"{warning_text}"
            )

        if route.task_type == "stock_recommendation_analysis" and market_result and market_result.get("clarification_question"):
            options = market_result.get("clarification_options", [])
            lines = [market_result["clarification_question"]]
            if options:
                lines.append("")
                lines.extend(f"- {item}" for item in options[:4])
            return "\n".join(lines)

        lines = [
            "以下分析基于当前公开数据、系统行情快照和已收录资料，不构成个性化投资建议。",
            "",
            f"任务类型：{route.task_type}",
        ]
        if support:
            lines.append("支持依据：")
            lines.extend(f"- {item}" for item in support)
        if risks:
            lines.append("")
            lines.append("风险与不确定性：")
            lines.extend(f"- {item}" for item in risks)
        if citations:
            lines.append("")
            lines.append("参考来源：")
            lines.extend(f"- {item.get('title', '--')} | {item.get('section_title') or '未分节'}" for item in citations[:3])
        if not support and not citations:
            lines.append("当前可用证据较少，建议补充财报、公告或研报后再做更深入判断。")
        lines.append("")
        lines.append(f"当前画像：风险偏好 {profile.risk_level}，期限 {profile.investment_horizon}。")
        if warning_text:
            lines.append(warning_text.strip())
        return "\n".join(lines)

    def _is_greeting_like(self, route: V2RouteDecision) -> bool:
        return route.reason == "识别为问候或轻量闲聊"

    def _fmt_turnover(self, value: Any) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "--"
        if abs(number) >= 100000000:
            return f"{number / 100000000:.2f} 亿元"
        if abs(number) >= 10000:
            return f"{number / 10000:.2f} 万元"
        return f"{number:.0f}"

    def _fmt_percent(self, value: Any) -> str:
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return "--"

    def _build_stock_detail_summary(self, market_result: dict[str, Any]) -> str:
        quote = market_result.get("quote", {}) or {}
        profile = market_result.get("profile", {}) or {}
        name = quote.get("name") or profile.get("company_name") or quote.get("symbol") or "该股"
        price = quote.get("last_price")
        change_percent = quote.get("change_percent")
        sector = profile.get("sector") or "待补充行业"
        industry = profile.get("industry") or "待补充细分"
        return f"{name} 当前价格 {price if price is not None else '--'}，涨跌幅 {self._fmt_percent(change_percent)}，所属 {sector} / {industry}。"

    def _build_stock_detail_items(self, market_result: dict[str, Any]) -> list[str]:
        quote = market_result.get("quote", {}) or {}
        profile = market_result.get("profile", {}) or {}
        technical = market_result.get("technical", {}) or {}
        capital_flow = market_result.get("capital_flow", {}) or {}
        news = market_result.get("news", []) or []

        items: list[str] = []
        if quote:
            items.append(
                f"{quote.get('symbol', '--')} | 最新价 {quote.get('last_price', '--')} | 涨跌幅 {self._fmt_percent(quote.get('change_percent'))}"
            )
            items.append(
                f"成交额 {self._fmt_turnover(quote.get('turnover'))} | 换手率 {self._fmt_percent(quote.get('turnover_rate'))} | 振幅 {self._fmt_percent(quote.get('amplitude'))}"
            )
        if profile:
            items.append(
                f"行业 {profile.get('sector') or '--'} / {profile.get('industry') or '--'} | PE {profile.get('pe') if profile.get('pe') is not None else '--'} | PB {profile.get('pb') if profile.get('pb') is not None else '--'}"
            )
            items.append(
                f"ROE {self._fmt_percent(profile.get('roe'))} | 负债率 {self._fmt_percent(profile.get('debt_ratio'))} | 股息率 {self._fmt_percent(profile.get('dividend_yield'))}"
            )
        if technical:
            items.append(
                f"技术面 RSI14 {technical.get('rsi14') if technical.get('rsi14') is not None else '--'} | MA5 {technical.get('ma5') if technical.get('ma5') is not None else '--'} | 趋势 {technical.get('momentum_label') or '--'}"
            )
        if capital_flow:
            items.append(
                f"资金流 {capital_flow.get('summary') or '--'} | 主力净流入 {self._fmt_turnover(capital_flow.get('main_net_inflow'))}"
            )
        if news:
            first_news = news[0]
            items.append(f"最新热点 {first_news.get('title', '--')} | {first_news.get('source', '--')}")
        return items[:6]

