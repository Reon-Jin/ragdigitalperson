from __future__ import annotations

import json
import re
from typing import Any, Sequence

from app.config import Settings
from app.services.deepseek_client import CompatibleLLMClient, ModelProvider


class MetadataService:
    def __init__(self, settings: Settings, llm_client: CompatibleLLMClient) -> None:
        self.settings = settings
        self.llm_client = llm_client

    async def enrich_document(
        self,
        *,
        filename: str,
        text_excerpt: str,
        headings: Sequence[str],
        chunks: Sequence[dict[str, Any]],
        model_provider: ModelProvider,
    ) -> dict[str, Any]:
        base = self._heuristic_document_metadata(filename, text_excerpt, headings, chunks)
        if not self.llm_client.is_configured(model_provider):
            return base

        try:
            doc_meta = await self.llm_client.json_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是资料整理助手。"
                            "请把资料分类到 金融、医学、法律、科技、生活 五类之一，"
                            "再生成一个准确的大标题、一句摘要和一组关键词。"
                            "只返回 JSON。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "filename": filename,
                                "headings": list(headings)[:12],
                                "excerpt": text_excerpt[: self.settings.metadata_excerpt_chars],
                                "output_schema": {
                                    "category": "金融|医学|法律|科技|生活",
                                    "title": "不超过30字的大标题",
                                    "summary": "不超过120字摘要",
                                    "keywords": ["3到8个关键词"],
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                provider=model_provider,
                temperature=0.1,
            )
        except Exception:
            doc_meta = {}

        chunk_titles = {}
        chunk_batches = self._chunk_batches(chunks, self.settings.chunk_title_batch_size)
        for batch in chunk_batches:
            try:
                batch_result = await self.llm_client.json_chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是资料切片命名助手。"
                                "请为每个分段生成一个准确、简洁的小标题。"
                                "只返回 JSON。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "filename": filename,
                                    "doc_title": doc_meta.get("title") or base["title"],
                                    "chunks": [
                                        {
                                            "chunk_id": item["chunk_id"],
                                            "section_title": item["section_title"],
                                            "preview": item["preview"],
                                        }
                                        for item in batch
                                    ],
                                    "output_schema": {
                                        "chunk_titles": {
                                            item["chunk_id"]: "不超过18字的小标题" for item in batch
                                        }
                                    },
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    provider=model_provider,
                    temperature=0.1,
                )
            except Exception:
                batch_result = {}

            if isinstance(batch_result.get("chunk_titles"), dict):
                chunk_titles.update(batch_result["chunk_titles"])

        enriched = dict(base)
        category = doc_meta.get("category")
        if category in self.settings.allowed_categories:
            enriched["category"] = category

        title = str(doc_meta.get("title", "")).strip()
        if title:
            enriched["title"] = title[:120]

        summary = str(doc_meta.get("summary", "")).strip()
        if summary:
            enriched["summary"] = summary[:280]

        keywords = self._normalize_keywords(doc_meta.get("keywords"))
        if keywords:
            enriched["keywords"] = keywords

        normalized_chunk_titles = {}
        for chunk in chunks:
            title_value = str(chunk_titles.get(chunk["chunk_id"], "")).strip()
            normalized_chunk_titles[chunk["chunk_id"]] = title_value[:80] or chunk["chunk_title"]
        enriched["chunk_titles"] = normalized_chunk_titles
        return enriched

    def _heuristic_document_metadata(
        self,
        filename: str,
        text_excerpt: str,
        headings: Sequence[str],
        chunks: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        probe = f"{filename}\n{text_excerpt}".lower()
        keyword_map = {
            "金融": ["金融", "股票", "投资", "基金", "银行", "market", "finance"],
            "医学": ["医学", "疾病", "患者", "治疗", "clinical", "medical", "health"],
            "法律": ["法律", "法规", "合同", "司法", "判决", "legal", "law"],
            "科技": ["rag", "llm", "模型", "算法", "技术", "系统", "ai", "research"],
            "生活": ["生活", "家庭", "教育", "旅行", "日常", "daily", "lifestyle"],
        }
        category = "生活"
        for name, keywords in keyword_map.items():
            if any(keyword in probe for keyword in keywords):
                category = name
                break

        first_heading = next((item for item in headings if item.strip()), "")
        title = first_heading or self._first_sentence(text_excerpt) or re.sub(r"\.[^.]+$", "", filename)
        summary = self._first_sentence(text_excerpt, 120)
        chunk_titles = {chunk["chunk_id"]: chunk["chunk_title"] for chunk in chunks}
        keywords = self._fallback_keywords(filename, text_excerpt, headings, chunk_titles.values())
        return {
            "category": category,
            "title": title[:120],
            "summary": summary[:280],
            "keywords": keywords,
            "chunk_titles": chunk_titles,
        }

    def _first_sentence(self, text: str, limit: int = 28) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        sentence = re.split(r"[。！？.!?；;]", cleaned)[0].strip()
        if len(sentence) > limit:
            return sentence[:limit].rstrip()
        return sentence or "资料概览"

    def _chunk_batches(self, chunks: Sequence[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
        return [list(chunks[index:index + batch_size]) for index in range(0, len(chunks), batch_size)]

    def _normalize_keywords(self, values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        keywords: list[str] = []
        for value in values:
            cleaned = re.sub(r"\s+", " ", str(value)).strip(" ,;，；")
            if len(cleaned) < 2 or len(cleaned) > 24:
                continue
            if cleaned not in keywords:
                keywords.append(cleaned)
            if len(keywords) >= 8:
                break
        return keywords

    def _fallback_keywords(
        self,
        filename: str,
        text_excerpt: str,
        headings: Sequence[str],
        chunk_titles: Sequence[str],
    ) -> list[str]:
        source = " ".join([filename, *headings[:6], *list(chunk_titles)[:6], text_excerpt[:800]])
        chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", source)
        english_terms = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{3,18}\b", source.lower())
        stop_words = {"using", "based", "study", "method", "results", "chapter", "section", "introduction"}
        keywords: list[str] = []
        for candidate in [*chinese_terms, *[item for item in english_terms if item not in stop_words]]:
            if candidate not in keywords:
                keywords.append(candidate)
            if len(keywords) >= 8:
                break
        return keywords
