from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Sequence

from app.config import Settings
from app.services.deepseek_client import CompatibleLLMClient, ModelProvider
from app.services.document_store import DocumentStore, SearchResult


class RagEngine:
    def __init__(self, settings: Settings, document_store: DocumentStore, llm_client: CompatibleLLMClient) -> None:
        self.settings = settings
        self.document_store = document_store
        self.llm_client = llm_client

    async def judge_need_retrieval(self, message: str, *, model_provider: ModelProvider) -> dict[str, Any]:
        heuristic = self._heuristic_need_retrieval(message)
        if not self.llm_client.is_configured(model_provider):
            return heuristic

        payload = {
            "user_query": message,
            "available_categories": list(self.settings.allowed_categories),
            "instruction": "判断这个问题是否需要检索用户上传的专业资料。如果不需要，则说明原因。",
            "output_schema": {
                "should_retrieve": True,
                "mode": "none|shallow|deep",
                "reason": "20字内说明",
                "query_rewrites": ["最多4个检索查询"],
                "domain_hints": ["从五类里选0到3个"],
            },
        }

        try:
            result = await self.llm_client.json_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是检索决策器。你必须先判断是否需要查用户上传的专业资料，"
                            "再给出检索深度和检索查询改写。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                provider=model_provider,
                temperature=0.1,
            )
        except Exception:
            return heuristic

        should_retrieve = bool(result.get("should_retrieve", heuristic["should_retrieve"]))
        mode = str(result.get("mode", heuristic["mode"]))
        if mode not in {"none", "shallow", "deep"}:
            mode = heuristic["mode"]

        domain_hints = [
            item
            for item in result.get("domain_hints", [])
            if item in self.settings.allowed_categories
        ]
        query_rewrites = self._normalize_queries(result.get("query_rewrites") or [], message)

        return {
            "should_retrieve": should_retrieve,
            "mode": mode,
            "reason": str(result.get("reason", heuristic["reason"]))[:120],
            "queries": query_rewrites or heuristic["queries"],
            "target_granularity": "chunk",
            "selected_categories": domain_hints,
            "selected_documents": [],
            "selected_chunk_ids": [],
        }

    def _heuristic_need_retrieval(self, message: str) -> dict[str, Any]:
        lower = message.lower().strip()
        should_retrieve = True
        mode = "deep"
        reason = "需要依赖资料"

        if any(token in lower for token in ["你好", "hello", "hi", "谢谢", "再见"]):
            should_retrieve = False
            mode = "none"
            reason = "寒暄类问题"
        elif any(token in lower for token in ["写诗", "讲故事", "起名字", "闲聊", "自我介绍"]):
            should_retrieve = False
            mode = "none"
            reason = "创意型直接回答"
        elif len(lower) < 12:
            mode = "shallow"
            reason = "短问题先浅检索"

        hints = [category for category in self.settings.allowed_categories if category in message][:2]
        return {
            "should_retrieve": should_retrieve,
            "mode": mode,
            "reason": reason,
            "queries": self._normalize_queries([message, self._keyword_query(message), f"{message} 核心概念"], message),
            "target_granularity": "chunk",
            "selected_categories": hints,
            "selected_documents": [],
            "selected_chunk_ids": [],
        }

    def _keyword_query(self, message: str) -> str:
        cleaned = (
            message.replace("什么是", "")
            .replace("请解释", "")
            .replace("帮我", "")
            .replace("根据资料", "")
            .replace("根据文档", "")
            .strip("？?。.! ")
        )
        return cleaned or message

    def _normalize_queries(self, queries: Sequence[str], message: str) -> list[str]:
        unique: list[str] = []
        for query in [message, *queries]:
            if not isinstance(query, str):
                continue
            cleaned = " ".join(query.split()).strip()
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
            if len(unique) >= 4:
                break
        return unique

    async def _select_categories(self, message: str, plan: dict[str, Any], *, model_provider: ModelProvider) -> list[str]:
        available = self.document_store.categories_summary()
        if not available:
            return []

        if not self.llm_client.is_configured(model_provider):
            hinted = [item for item in plan.get("selected_categories", []) if item in self.settings.allowed_categories]
            return hinted or [available[0]["category"]]

        payload = {
            "user_query": message,
            "available_categories": available,
            "instruction": "从这些资料类型中选择与问题最相关的一个或多个类型。",
            "output_schema": {
                "categories": ["可多选，必须来自 available_categories"],
                "reason": "15字内",
            },
        }
        try:
            result = await self.llm_client.json_chat(
                [
                    {"role": "system", "content": "你是资料类型选择器。只返回 JSON。"},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                provider=model_provider,
                temperature=0.1,
            )
        except Exception:
            hinted = [item for item in plan.get("selected_categories", []) if item in self.settings.allowed_categories]
            return hinted or [available[0]["category"]]

        categories = [item for item in result.get("categories", []) if item in self.settings.allowed_categories]
        return categories[:3] or [available[0]["category"]]

    async def _select_documents(
        self,
        message: str,
        categories: Sequence[str],
        queries: Sequence[str],
        *,
        model_provider: ModelProvider,
    ) -> list[str]:
        ranked_docs = self.document_store.rank_documents(queries, categories=categories, limit=12)
        if not ranked_docs:
            return []

        if not self.llm_client.is_configured(model_provider):
            return [item["doc_id"] for item in ranked_docs[: min(2, len(ranked_docs))]]

        payload = {
            "user_query": message,
            "candidate_documents": [
                {
                    "doc_id": item["doc_id"],
                    "category": item["category"],
                    "title": item["title"],
                    "filename": item["filename"],
                    "summary": item["summary"],
                    "score": item.get("score", 0.0),
                }
                for item in ranked_docs
            ],
            "instruction": "选择最相关的一个或多个资料，支持多选。",
            "output_schema": {
                "doc_ids": ["可多选，必须来自 candidate_documents.doc_id"],
                "reason": "15字内",
            },
        }

        try:
            result = await self.llm_client.json_chat(
                [
                    {"role": "system", "content": "你是资料标题选择器。只返回 JSON。"},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                provider=model_provider,
                temperature=0.1,
            )
        except Exception:
            return [item["doc_id"] for item in ranked_docs[: min(2, len(ranked_docs))]]

        doc_ids = [item for item in result.get("doc_ids", []) if any(doc["doc_id"] == item for doc in ranked_docs)]
        if not doc_ids:
            doc_ids = [item["doc_id"] for item in ranked_docs[: min(2, len(ranked_docs))]]
        return doc_ids[: self.settings.multi_select_doc_limit]

    async def _select_chunks(
        self,
        message: str,
        doc_ids: Sequence[str],
        queries: Sequence[str],
        *,
        model_provider: ModelProvider,
    ) -> list[str]:
        scored_candidates = self.document_store.rank_chunks(queries, doc_ids=doc_ids, limit=24)
        candidate_map = {item.chunk_id: item for item in scored_candidates}

        if len(candidate_map) < 12:
            for candidate in self.document_store.get_chunk_candidates_for_docs(doc_ids, limit_per_doc=6):
                candidate_map.setdefault(
                    candidate["chunk_id"],
                    SearchResult(
                        doc_id=candidate["doc_id"],
                        filename=self.document_store.docs_by_id[candidate["doc_id"]]["filename"],
                        category=candidate["category"],
                        title=candidate["doc_title"],
                        section_id=candidate["section_id"],
                        section_title=candidate["section_title"],
                        chunk_id=candidate["chunk_id"],
                        chunk_index=candidate["chunk_index"],
                        chunk_title=candidate["chunk_title"],
                        score=0.0,
                        text=candidate["preview"],
                    ),
                )

        candidates = list(candidate_map.values())[:24]
        if not candidates:
            return []

        if not self.llm_client.is_configured(model_provider):
            return [item.chunk_id for item in candidates[: min(4, len(candidates))]]

        payload = {
            "user_query": message,
            "candidate_chunks": [
                {
                    "chunk_id": item.chunk_id,
                    "category": item.category,
                    "doc_title": item.title,
                    "section_title": item.section_title,
                    "chunk_title": item.chunk_title,
                    "preview": item.text[:180],
                    "score": item.score,
                }
                for item in candidates
            ],
            "instruction": "请选择最有帮助的多个分段小标题作为证据。",
            "output_schema": {
                "chunk_ids": ["可多选，必须来自 candidate_chunks.chunk_id"],
                "reason": "15字内",
            },
        }
        try:
            result = await self.llm_client.json_chat(
                [
                    {"role": "system", "content": "你是分段小标题选择器。只返回 JSON。"},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                provider=model_provider,
                temperature=0.1,
            )
        except Exception:
            return [item.chunk_id for item in candidates[: min(4, len(candidates))]]

        chunk_ids = [item for item in result.get("chunk_ids", []) if any(candidate.chunk_id == item for candidate in candidates)]
        if not chunk_ids:
            chunk_ids = [item.chunk_id for item in candidates[: min(4, len(candidates))]]
        return chunk_ids[: self.settings.multi_select_chunk_limit]

    def _context_block(self, contexts: Sequence[SearchResult]) -> str:
        if not contexts:
            return "没有检索到可靠资料。请明确告诉用户当前资料不足。"
        return "\n\n".join(
            (
                f"[资料 {index + 1}] 类型: {item.category}\n"
                f"文件: {item.filename}\n"
                f"资料标题: {item.title}\n"
                f"章节: {item.section_title}\n"
                f"分段标题: {item.chunk_title}\n"
                f"片段序号: {item.chunk_index}\n"
                f"内容: {item.text}"
            )
            for index, item in enumerate(contexts)
        )

    def _emotion_from_answer(self, answer: str) -> str:
        if any(token in answer for token in ["抱歉", "不足", "无法确认", "没有足够"]):
            return "concerned"
        if any(token in answer for token in ["建议", "注意", "风险", "谨慎"]):
            return "serious"
        if any(token in answer for token in ["很好", "可以", "已经完成", "恭喜"]):
            return "happy"
        if any(token in answer for token in ["核心", "首先", "其次", "总结"]):
            return "serious"
        return "neutral"

    async def retrieve(
        self,
        message: str,
        *,
        model_provider: ModelProvider,
    ) -> tuple[dict[str, Any], list[SearchResult], list[dict[str, Any]]]:
        plan = await self.judge_need_retrieval(message, model_provider=model_provider)
        trace: list[dict[str, Any]] = []
        contexts: list[SearchResult] = []

        if not plan["should_retrieve"]:
            return plan, contexts, trace

        categories = await self._select_categories(message, plan, model_provider=model_provider)
        plan["selected_categories"] = categories
        queries = plan["queries"] or [message]

        doc_ids = await self._select_documents(message, categories, queries, model_provider=model_provider)
        plan["selected_documents"] = doc_ids

        chunk_ids = await self._select_chunks(message, doc_ids, queries, model_provider=model_provider)
        plan["selected_chunk_ids"] = chunk_ids

        if chunk_ids:
            contexts = self.document_store.rank_chunks(queries, categories=categories, doc_ids=doc_ids, chunk_ids=chunk_ids, limit=self.settings.top_k)
        else:
            contexts = self.document_store.rank_chunks(queries, categories=categories, doc_ids=doc_ids, limit=self.settings.top_k)

        if not contexts:
            contexts, trace = self.document_store.hierarchical_search(queries, categories=categories, doc_ids=doc_ids, chunk_ids=chunk_ids)
        else:
            for category in categories:
                trace.append({"id": category, "label": category, "score": 1.0, "level": "category", "parent_id": None})
            for doc_id in doc_ids:
                doc = self.document_store.docs_by_id.get(doc_id)
                if doc:
                    trace.append(
                        {
                            "id": doc_id,
                            "label": doc["title"],
                            "score": 1.0,
                            "level": "document",
                            "parent_id": doc["category"],
                        }
                    )
            for item in contexts:
                trace.append(
                    {
                        "id": item.chunk_id,
                        "label": item.chunk_title,
                        "score": item.score,
                        "level": "chunk",
                        "parent_id": item.doc_id,
                    }
                )

        return plan, contexts, trace

    def _answer_messages(self, message: str, plan: dict[str, Any], contexts: Sequence[SearchResult]) -> list[dict[str, str]]:
        if plan["should_retrieve"]:
            system = (
                "你是一个基于用户私有资料回答问题的专业助手。"
                "只能优先依据给定资料回答，不要编造。"
                "若资料不足，要明确说明不足。"
                "回答要清晰、有条理，并在最后单独给出“参考资料：”一行。"
            )
            user = (
                f"用户问题：{message}\n\n"
                f"检索决策：{plan['mode']} / {plan['reason']}\n"
                f"资料类型：{', '.join(plan.get('selected_categories', [])) or '未限定'}\n"
                f"资料标题数量：{len(plan.get('selected_documents', []))}\n"
                f"候选分段数量：{len(plan.get('selected_chunk_ids', []))}\n\n"
                f"可用资料：\n{self._context_block(contexts)}\n\n"
                "请输出专业、准确、简洁的答案。"
            )
            return [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]

        return [
            {
                "role": "system",
                "content": "你是一个友好的数字人助手。当前问题不需要检索资料，请直接简洁回答。",
            },
            {"role": "user", "content": message},
        ]

    async def answer_once(self, message: str, *, model_provider: ModelProvider) -> dict[str, Any]:
        plan, contexts, trace = await self.retrieve(message, model_provider=model_provider)
        answer = await self.llm_client.chat(
            self._answer_messages(message, plan, contexts),
            provider=model_provider,
            temperature=0.2,
        )
        return {
            "answer": answer,
            "sources": contexts,
            "plan": plan,
            "emotion": self._emotion_from_answer(answer),
            "trace": trace,
        }

    async def stream_answer(self, message: str, *, model_provider: ModelProvider) -> AsyncIterator[dict[str, Any]]:
        plan, contexts, trace = await self.retrieve(message, model_provider=model_provider)
        yield {"type": "plan", "plan": plan, "trace": trace}

        collected: list[str] = []
        async for delta in self.llm_client.stream_chat(
            self._answer_messages(message, plan, contexts),
            provider=model_provider,
            temperature=0.2,
        ):
            collected.append(delta)
            yield {"type": "token", "delta": delta}

        answer = "".join(collected).strip()
        yield {
            "type": "final",
            "answer": answer,
            "emotion": self._emotion_from_answer(answer),
            "sources": [self._source_payload(item) for item in contexts],
            "plan": plan,
            "trace": trace,
        }

    def _source_payload(self, item: SearchResult) -> dict[str, Any]:
        preview = item.text[:180] + "..." if len(item.text) > 180 else item.text
        return {
            "doc_id": item.doc_id,
            "filename": item.filename,
            "category": item.category,
            "title": item.title,
            "section_id": item.section_id,
            "section_title": item.section_title,
            "chunk_id": item.chunk_id,
            "chunk_index": item.chunk_index,
            "chunk_title": item.chunk_title,
            "score": item.score,
            "preview": preview,
        }
