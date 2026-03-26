from __future__ import annotations

import re
from typing import Any

from app.knowledge_base.finance_store import FinanceKnowledgeBase, TASK_SECTION_PRIORITIES
from app.services.mysql_document_store import DocumentStore, SearchResult


FINANCE_KEYWORDS = (
    "\u80a1\u7968",
    "\u4e2a\u80a1",
    "\u516c\u53f8",
    "\u8d22\u62a5",
    "\u5e74\u62a5",
    "\u5b63\u62a5",
    "\u516c\u544a",
    "\u4e1a\u7ee9",
    "\u5229\u6da6",
    "\u8425\u6536",
    "\u4f30\u503c",
    "\u884c\u4e1a",
    "\u677f\u5757",
    "\u653f\u7b56",
    "\u98ce\u9669",
    "\u57fa\u91d1",
    "\u503a\u5238",
    "\u94f6\u884c",
    "\u4fdd\u9669",
    "\u534a\u5bfc\u4f53",
    "\u65b0\u80fd\u6e90",
    "\u533b\u836f",
    "ai",
)
RISK_TERMS = (
    "\u98ce\u9669",
    "\u6ce2\u52a8",
    "\u4e0b\u6ed1",
    "\u538b\u529b",
    "\u4e0d\u786e\u5b9a",
    "\u51cf\u503c",
    "\u4e8f\u635f",
)
METRIC_TERMS = (
    "\u8425\u6536",
    "\u5229\u6da6",
    "\u51c0\u5229\u6da6",
    "\u73b0\u91d1\u6d41",
    "\u6bdb\u5229\u7387",
    "\u540c\u6bd4",
    "\u73af\u6bd4",
)
POSITIVE_TERMS = (
    "\u589e\u957f",
    "\u63d0\u5347",
    "\u6539\u5584",
    "\u4e0a\u5347",
    "\u6269\u5927",
    "\u4f18\u5316",
)
NEGATIVE_TERMS = (
    "\u4e0b\u964d",
    "\u4e0b\u6ed1",
    "\u627f\u538b",
    "\u6076\u5316",
    "\u6536\u7f29",
    "\u8f6c\u5f31",
)
TASK_QUERY_TEMPLATES = {
    "general_finance_qa": [
        "{query} \u5b9a\u4e49 \u903b\u8f91 \u98ce\u9669",
        "{query} \u9002\u7528\u573a\u666f \u5e38\u89c1\u8bef\u533a",
    ],
    "stock_analysis": [
        "{anchor} \u516c\u53f8\u7b80\u4ecb \u4e3b\u8425\u4e1a\u52a1 \u884c\u4e1a \u98ce\u9669",
        "{anchor} \u8d22\u62a5 \u516c\u544a \u8d22\u52a1\u4eae\u70b9 \u4f30\u503c",
    ],
    "earnings_report_analysis": [
        "{anchor} \u8d22\u62a5 \u8425\u6536 \u5229\u6da6 \u6bdb\u5229\u7387 \u73b0\u91d1\u6d41 \u540c\u6bd4 \u73af\u6bd4",
        "{anchor} \u7ba1\u7406\u5c42\u8ba8\u8bba \u98ce\u9669\u56e0\u7d20 \u8d22\u52a1\u62a5\u8868\u9644\u6ce8",
    ],
    "news_explainer": [
        "{query} \u65b0\u95fb \u516c\u544a \u653f\u7b56 \u539f\u56e0 \u5f71\u54cd",
        "{query} \u77ed\u671f\u5f71\u54cd \u4e2d\u671f\u5f71\u54cd \u98ce\u9669",
    ],
    "sector_analysis": [
        "{anchor} \u884c\u4e1a\u73b0\u72b6 \u9a71\u52a8\u56e0\u7d20 \u7ade\u4e89\u683c\u5c40 \u98ce\u9669",
        "{anchor} \u653f\u7b56 \u91cd\u70b9\u516c\u53f8 \u9f99\u5934 \u7814\u62a5",
    ],
    "portfolio_assistant": [
        "{query} \u98ce\u9669\u504f\u597d \u6295\u8d44\u671f\u9650 \u98ce\u9669\u63d0\u793a",
        "{query} \u8d44\u4ea7\u7c7b\u522b \u6ce2\u52a8 \u56de\u64a4",
    ],
    "teaching_mode": [
        "{query} \u901a\u4fd7\u89e3\u91ca \u4e3e\u4f8b \u98ce\u9669",
        "{query} \u521d\u5b66\u8005 \u79d1\u666e",
    ],
}
TASK_DOC_TYPE_BONUS = {
    "stock_analysis": {"annual_report": 1.2, "quarterly_report": 1.2, "announcement": 1.0, "research": 0.8},
    "earnings_report_analysis": {"annual_report": 1.8, "quarterly_report": 1.8, "announcement": 1.0, "research": 0.6},
    "news_explainer": {"news": 1.6, "announcement": 1.2, "policy": 1.4, "research": 0.7},
    "sector_analysis": {"research": 1.6, "policy": 1.2, "news": 0.8, "annual_report": 0.6},
}
KPI_DEFINITIONS = {
    "revenue": {"label": "Revenue", "aliases": ("\u8425\u4e1a\u6536\u5165", "\u8425\u6536")},
    "net_profit": {"label": "Net Profit", "aliases": ("\u5f52\u6bcd\u51c0\u5229\u6da6", "\u51c0\u5229\u6da6")},
    "operating_profit": {"label": "Operating Profit", "aliases": ("\u8425\u4e1a\u5229\u6da6",)},
    "gross_margin": {"label": "Gross Margin", "aliases": ("\u6bdb\u5229\u7387",)},
    "operating_cash_flow": {"label": "Operating Cash Flow", "aliases": ("\u7ecf\u8425\u6d3b\u52a8\u4ea7\u751f\u7684\u73b0\u91d1\u6d41\u91cf\u51c0\u989d", "\u7ecf\u8425\u73b0\u91d1\u6d41")},
    "yoy": {"label": "YoY", "aliases": ("\u540c\u6bd4",)},
    "qoq": {"label": "QoQ", "aliases": ("\u73af\u6bd4",)},
}
VALUE_PATTERN = r"[-+]?\d+(?:\.\d+)?(?:%|\u4ebf\u5143|\u4ebf|\u4e07\u5143|\u4e07|\u5143|\u500d)"


class FinanceRetriever:
    def __init__(self, document_store: DocumentStore, finance_kb: FinanceKnowledgeBase) -> None:
        self.document_store = document_store
        self.finance_kb = finance_kb

    def retrieve(
        self,
        query: str,
        *,
        task_type: str,
        user_id: str | None = None,
        company: str | None = None,
        ticker: str | None = None,
        sector: str | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        strategy = self._build_strategy(query, task_type=task_type, company=company, ticker=ticker, sector=sector)
        queries = strategy["queries"]

        meta_docs = self.finance_kb.search_documents(
            query,
            company=company,
            ticker=ticker,
            sector=sector,
            limit=10,
        )
        vector_docs = self.document_store.rank_documents(queries, user_id=user_id, limit=12)
        docs = self._merge_document_candidates(meta_docs, vector_docs, task_type=task_type)
        doc_ids = [item["doc_id"] for item in docs[:4]]

        meta_chunks = self.finance_kb.search_chunk_candidates(query, task_type=task_type, doc_ids=doc_ids, limit=14)
        vector_chunks = self.document_store.rank_chunks(queries, doc_ids=doc_ids, user_id=user_id, limit=max(limit * 2, 10))
        chunks = self._merge_chunk_candidates(meta_chunks, vector_chunks, task_type=task_type, limit=limit)
        if not chunks:
            chunks, _ = self.document_store.hierarchical_search(queries, doc_ids=doc_ids, user_id=user_id)
            chunks = self._rerank_chunks_by_task(chunks, task_type=task_type, limit=limit)

        chunk_metadata = self.finance_kb.get_chunk_metadata_map([item.chunk_id for item in chunks[:limit]])
        evidence_summary = self._summarize_evidence(chunks[:limit], task_type=task_type, metadata_map=chunk_metadata)

        return {
            "queries": queries,
            "strategy": strategy,
            "documents": docs[:4],
            "chunks": chunks[:limit],
            "evidence_summary": evidence_summary,
        }

    def is_finance_query(self, query: str) -> bool:
        lowered = query.lower()
        if any(keyword in lowered for keyword in FINANCE_KEYWORDS):
            return True
        return bool(re.search(r"\b[036]\d{5}\b", lowered))

    def _build_strategy(
        self,
        query: str,
        *,
        task_type: str,
        company: str | None,
        ticker: str | None,
        sector: str | None,
    ) -> dict[str, Any]:
        anchor = company or ticker or sector or query.strip()
        queries = self._expand_queries(query, task_type=task_type, anchor=anchor, company=company, ticker=ticker, sector=sector)
        return {
            "task_type": task_type,
            "anchor": anchor,
            "doc_focus": list(TASK_DOC_TYPE_BONUS.get(task_type, {}).keys()) or ["upload", "annual_report", "quarterly_report"],
            "section_focus": list(TASK_SECTION_PRIORITIES.get(task_type, {}).keys()) or ["general"],
            "queries": queries,
        }

    def _expand_queries(
        self,
        query: str,
        *,
        task_type: str,
        anchor: str,
        company: str | None,
        ticker: str | None,
        sector: str | None,
    ) -> list[str]:
        expanded = [query.strip()]
        for template in TASK_QUERY_TEMPLATES.get(task_type, []):
            expanded.append(template.format(query=query.strip(), anchor=anchor))
        if company:
            expanded.append(f"{company} \u57fa\u672c\u9762 \u8d22\u52a1 \u98ce\u9669")
        if ticker:
            expanded.append(f"{ticker} \u516c\u544a \u8d22\u62a5 \u98ce\u9669")
        if sector:
            expanded.append(f"{sector} \u884c\u4e1a \u653f\u7b56 \u9f99\u5934 \u98ce\u9669")
        expanded.append(f"{query.strip()} \u98ce\u9669")

        unique: list[str] = []
        for item in expanded:
            cleaned = " ".join(item.split()).strip()
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
        return unique[:5]

    def _summarize_evidence(
        self,
        chunks: list[SearchResult],
        *,
        task_type: str,
        metadata_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        support: list[str] = []
        risks: list[str] = []
        metrics: list[str] = []
        management: list[str] = []
        business: list[str] = []
        drivers: list[str] = []
        timeline: list[str] = []
        section_hits: dict[str, int] = {}
        report_kpis: dict[str, str] = {}

        ordered_chunks = list(chunks)
        if task_type == "earnings_report_analysis":
            ordered_chunks.sort(
                key=lambda item: (
                    0 if (metadata_map.get(item.chunk_id, {}).get("chunk_kind") == "table" or item.chunk_kind == "table") else 1,
                    -float(item.score),
                )
            )

        for item in ordered_chunks:
            metadata = metadata_map.get(item.chunk_id, {})
            section_type = metadata.get("section_type") or "general"
            text = re.sub(r"\s+", " ", item.text).strip()
            bullet = text[:100] + ("..." if len(text) > 100 else "")

            section_hits[section_type] = section_hits.get(section_type, 0) + 1

            if any(token in text for token in RISK_TERMS):
                self._append_unique(risks, bullet, limit=4)
            else:
                self._append_unique(support, bullet, limit=4)

            if section_type == "management_discussion":
                self._append_unique(management, bullet, limit=4)
            if section_type == "business":
                self._append_unique(business, bullet, limit=4)
            if section_type in {"news", "policy", "announcement", "research_view"}:
                self._append_unique(drivers, bullet, limit=4)

            if metadata.get("report_period") or metadata.get("publish_date"):
                time_label = metadata.get("report_period") or metadata.get("publish_date")
                self._append_unique(timeline, f"{time_label} | {item.title} | {item.section_title}", limit=4)

            for metric in self._extract_metric_snippets(text):
                self._append_unique(metrics, metric, limit=5)

            if task_type == "earnings_report_analysis":
                self._update_report_kpis(report_kpis, text)

        report_verdict = self._build_report_verdict(report_kpis, risks)
        if task_type == "earnings_report_analysis" and report_verdict["summary"]:
            support.insert(0, report_verdict["summary"])

        return {
            "task_type": task_type,
            "support": support[:3],
            "risks": risks[:3],
            "metrics": metrics[:4],
            "management": management[:4],
            "business": business[:4],
            "drivers": drivers[:4] or support[:4],
            "timeline": timeline[:4],
            "section_hits": section_hits,
            "report_kpis": report_kpis,
            "report_verdict": report_verdict,
        }

    def _merge_document_candidates(
        self,
        meta_docs: list[dict[str, Any]],
        vector_docs: list[dict[str, Any]],
        *,
        task_type: str,
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(meta_docs):
            score = float(item.get("meta_score", 0.0)) + (len(meta_docs) - index) * 0.1
            score += TASK_DOC_TYPE_BONUS.get(task_type, {}).get(item.get("doc_type") or "", 0.0)
            merged[item["doc_id"]] = dict(item, blended_score=score)

        for index, item in enumerate(vector_docs):
            current = merged.get(item["doc_id"], dict(item))
            current["doc_id"] = item["doc_id"]
            current["title"] = current.get("title") or item.get("title")
            current["filename"] = current.get("filename") or item.get("filename")
            current["category"] = current.get("category") or item.get("category")
            current["summary"] = current.get("summary") or item.get("summary")
            current["blended_score"] = float(current.get("blended_score", 0.0)) + float(item.get("score", 0.0)) + (len(vector_docs) - index) * 0.05
            current["blended_score"] += TASK_DOC_TYPE_BONUS.get(task_type, {}).get(current.get("doc_type") or "", 0.0)
            merged[item["doc_id"]] = current

        ranked = sorted(merged.values(), key=lambda value: value.get("blended_score", 0.0), reverse=True)
        return ranked

    def _merge_chunk_candidates(
        self,
        meta_chunks: list[dict[str, Any]],
        vector_chunks: list[SearchResult],
        *,
        task_type: str,
        limit: int,
    ) -> list[SearchResult]:
        merged: dict[str, SearchResult] = {item.chunk_id: item for item in vector_chunks}
        metadata_map = self.finance_kb.get_chunk_metadata_map([item.chunk_id for item in vector_chunks])

        for result in merged.values():
            section_type = metadata_map.get(result.chunk_id, {}).get("section_type")
            result.score += self._chunk_section_bonus(task_type, section_type) * 0.15

        if meta_chunks:
            chunk_results = self.document_store.get_chunks_by_ids([item["chunk_id"] for item in meta_chunks])
            meta_result_map = {item.chunk_id: item for item in chunk_results}
            meta_score_map = {item["chunk_id"]: float(item.get("meta_score", 0.0)) for item in meta_chunks}
            meta_section_map = {item["chunk_id"]: item.get("section_type") for item in meta_chunks}
            for chunk_id, result in meta_result_map.items():
                existing = merged.get(chunk_id)
                boosted_score = result.score + meta_score_map.get(chunk_id, 0.0) * 0.1
                boosted_score += self._chunk_section_bonus(task_type, meta_section_map.get(chunk_id)) * 0.15
                if existing:
                    existing.score = max(existing.score, boosted_score)
                else:
                    result.score = boosted_score
                    merged[chunk_id] = result

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def _rerank_chunks_by_task(self, chunks: list[SearchResult], *, task_type: str, limit: int) -> list[SearchResult]:
        metadata_map = self.finance_kb.get_chunk_metadata_map([item.chunk_id for item in chunks])
        for item in chunks:
            section_type = metadata_map.get(item.chunk_id, {}).get("section_type")
            item.score += self._chunk_section_bonus(task_type, section_type) * 0.12
        ranked = sorted(chunks, key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def _chunk_section_bonus(self, task_type: str, section_type: str | None) -> float:
        if not section_type:
            return 0.0
        return float(TASK_SECTION_PRIORITIES.get(task_type, {}).get(section_type, 0.0))

    def _extract_metric_snippets(self, text: str) -> list[str]:
        metrics: list[str] = []
        compact = re.sub(r"\s+", " ", text)
        patterns = (
            r"(?:\u8425\u6536|\u5229\u6da6|\u51c0\u5229\u6da6|\u73b0\u91d1\u6d41|\u6bdb\u5229\u7387|\u540c\u6bd4|\u73af\u6bd4)[^\n,.，。;；]{0,36}",
            r"\d+(?:\.\d+)?(?:%|\u4ebf|\u4e07|\u500d)",
        )
        for pattern in patterns:
            for match in re.findall(pattern, compact):
                cleaned = match.strip(" ,.;，。；")
                if not cleaned:
                    continue
                if pattern.startswith(r"(?:") and not any(term in cleaned for term in METRIC_TERMS):
                    continue
                self._append_unique(metrics, cleaned, limit=5)
        return metrics

    def _update_report_kpis(self, report_kpis: dict[str, str], text: str) -> None:
        compact = re.sub(r"\s+", " ", text)
        for key, definition in KPI_DEFINITIONS.items():
            if key in report_kpis:
                continue
            snippet = self._match_kpi_snippet(compact, definition["aliases"])
            if snippet:
                report_kpis[key] = f"{definition['label']}: {snippet}"

    def _match_kpi_snippet(self, text: str, aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            pattern = rf"{re.escape(alias)}[^\n,.，。;；:：]{{0,20}}(?:{VALUE_PATTERN})?"
            for match in re.findall(pattern, text):
                cleaned = match.strip(" ,.;，。；:：")
                if not cleaned or alias not in cleaned:
                    continue
                if re.search(VALUE_PATTERN, cleaned) or alias in {"\u540c\u6bd4", "\u73af\u6bd4"}:
                    return cleaned
        return None

    def _build_report_verdict(self, report_kpis: dict[str, str], risks: list[str]) -> dict[str, str]:
        if not report_kpis:
            return {
                "label": "watch",
                "tone": "cautious",
                "summary": "Current report evidence is insufficient for a stable earnings verdict.",
            }

        positive = 0
        negative = 0
        for key, value in report_kpis.items():
            lower_value = value.lower()
            if re.search(r"(?<!\d)-\d+(?:\.\d+)?%", value):
                negative += 2
            elif re.search(r"(?:^|[^\d])\+?\d+(?:\.\d+)?%", value):
                positive += 1
            if any(token in lower_value for token in POSITIVE_TERMS):
                positive += 1
            if any(token in lower_value for token in NEGATIVE_TERMS):
                negative += 1
            if key in {"revenue", "net_profit", "operating_cash_flow"} and re.search(r"-\d+(?:\.\d+)?", value):
                negative += 1

        negative += min(len(risks), 2)

        if positive >= negative + 2:
            return {
                "label": "improving",
                "tone": "positive",
                "summary": "Overall report tone looks improving, but it still needs to be checked against risk disclosures and cash flow quality.",
            }
        if negative >= positive + 2:
            return {
                "label": "deteriorating",
                "tone": "cautious",
                "summary": "Current report evidence points to weakening momentum or higher pressure. A cautious read is warranted.",
            }
        return {
            "label": "watch",
            "tone": "neutral",
            "summary": "The report shows mixed signals. It is better treated as watch-and-verify rather than clearly improving or deteriorating.",
        }

    def _append_unique(self, target: list[str], item: str, *, limit: int) -> None:
        if item and item not in target and len(target) < limit:
            target.append(item)
