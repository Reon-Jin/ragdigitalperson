from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from app.config import Settings
from app.storage.database import Database


REPORT_TERMS = {
    "annual_report": ("\u5e74\u62a5",),
    "quarterly_report": ("\u5b63\u62a5", "\u4e09\u5b63\u62a5", "\u4e2d\u62a5", "\u534a\u5e74\u62a5"),
    "announcement": ("\u516c\u544a", "\u63d0\u793a\u6027\u516c\u544a"),
    "research": ("\u7814\u62a5", "\u6df1\u5ea6\u62a5\u544a", "\u70b9\u8bc4"),
    "policy": ("\u653f\u7b56", "\u901a\u77e5", "\u6307\u5f15", "\u529e\u6cd5"),
    "news": ("\u65b0\u95fb", "\u5feb\u8baf", "\u8d44\u8baf"),
}
INDUSTRY_TERMS = (
    "\u65b0\u80fd\u6e90",
    "\u534a\u5bfc\u4f53",
    "\u94f6\u884c",
    "\u4fdd\u9669",
    "\u533b\u836f",
    "\u767d\u9152",
    "AI",
    "\u519b\u5de5",
    "\u5730\u4ea7",
    "\u6c7d\u8f66",
)
COMPANY_SUFFIXES = (
    "\u80a1\u4efd",
    "\u96c6\u56e2",
    "\u94f6\u884c",
    "\u4fdd\u9669",
    "\u79d1\u6280",
    "\u836f\u4e1a",
    "\u7535\u5b50",
    "\u80fd\u6e90",
    "\u6c7d\u8f66",
)
RISK_TERMS = (
    "\u98ce\u9669",
    "\u4e0d\u786e\u5b9a",
    "\u538b\u529b",
    "\u4e8f\u635f",
    "\u51cf\u503c",
)
SECTION_TYPE_RULES = {
    "risk": ("\u98ce\u9669", "\u4e0d\u786e\u5b9a", "\u63d0\u793a"),
    "financial_statement": ("\u8d44\u4ea7\u8d1f\u503a\u8868", "\u5229\u6da6\u8868", "\u73b0\u91d1\u6d41\u91cf\u8868", "\u8d22\u52a1\u62a5\u8868"),
    "management_discussion": ("\u7ba1\u7406\u5c42", "\u7ecf\u8425\u60c5\u51b5", "md&a", "\u8ba8\u8bba"),
    "announcement": ("\u516c\u544a", "\u63d0\u793a\u6027\u516c\u544a"),
    "policy": ("\u653f\u7b56", "\u901a\u77e5", "\u6307\u5f15", "\u529e\u6cd5"),
    "news": ("\u65b0\u95fb", "\u5feb\u8baf", "\u8d44\u8baf"),
    "research_view": ("\u7814\u62a5", "\u6295\u8d44\u8981\u70b9", "\u89c2\u70b9", "\u6838\u5fc3\u89c2\u70b9"),
    "business": ("\u516c\u53f8\u7b80\u4ecb", "\u4e3b\u8425", "\u4e1a\u52a1", "\u4ea7\u54c1", "\u6a21\u5f0f"),
    "notes": ("\u9644\u6ce8",),
}
TASK_SECTION_PRIORITIES = {
    "stock_analysis": {"business": 1.4, "management_discussion": 1.3, "risk": 1.4, "announcement": 1.2},
    "earnings_report_analysis": {"financial_statement": 1.6, "management_discussion": 1.5, "risk": 1.4, "notes": 1.3},
    "news_explainer": {"news": 1.6, "announcement": 1.5, "policy": 1.5, "research_view": 1.1},
    "sector_analysis": {"research_view": 1.5, "policy": 1.3, "business": 1.1, "risk": 1.2},
}


class FinanceKnowledgeBase:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = self.settings.finance_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.database_url, self.db_path)
        self.documents_table = "finance_documents"
        self.sections_table = "finance_sections"
        self.chunks_table = "finance_chunks"
        self.pages_table = "finance_pages"
        self.entities_table = "finance_entities"
        self.relations_table = "finance_relations"
        self._init_db()
        self._bootstrap_legacy_sqlite()

    def _build_in_clause(self, column: str, values: list[str], prefix: str) -> tuple[str, dict[str, Any]]:
        placeholders: list[str] = []
        params: dict[str, Any] = {}
        for index, value in enumerate(values):
            key = f"{prefix}_{index}"
            placeholders.append(f"%({key})s")
            params[key] = value
        return f"{column} IN ({', '.join(placeholders)})", params

    def _bootstrap_legacy_sqlite(self) -> None:
        if self.db.backend != "mysql" or not self.db_path.exists():
            return
        if int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.documents_table}", default=0) or 0) > 0:
            return
        legacy = sqlite3.connect(self.db_path)
        legacy.row_factory = sqlite3.Row
        table_map = {
            "documents": (self.documents_table, None),
            "sections": (self.sections_table, None),
            "chunks": (self.chunks_table, None),
            "pages": (self.pages_table, ["doc_id", "page_number", "char_start", "char_end", "preview"]),
            "entities": (self.entities_table, ["doc_id", "chunk_id", "entity_type", "entity_name", "normalized_name", "weight"]),
            "relations": (self.relations_table, ["doc_id", "subject_name", "relation_type", "object_name", "weight"]),
        }
        try:
            for source_table, (target_table, selected_columns) in table_map.items():
                try:
                    rows = [dict(row) for row in legacy.execute(f"SELECT * FROM {source_table}").fetchall()]
                except sqlite3.OperationalError:
                    continue
                if not rows:
                    continue
                columns = selected_columns or list(rows[0].keys())
                payload = [{column: row.get(column) for column in columns} for row in rows]
                statement = (
                    f"INSERT INTO {target_table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
                )
                self.db.execute_many(statement, payload)
        finally:
            legacy.close()

    def _init_db(self) -> None:
        statements = [
            f"""
            CREATE TABLE IF NOT EXISTS {self.documents_table} (
                doc_id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                category VARCHAR(64) NULL,
                doc_type VARCHAR(64) NULL,
                company_name VARCHAR(255) NULL,
                ticker VARCHAR(32) NULL,
                industry VARCHAR(128) NULL,
                publish_date VARCHAR(32) NULL,
                report_period VARCHAR(64) NULL,
                summary TEXT NULL,
                uploaded_at VARCHAR(40) NULL,
                chunk_count INTEGER DEFAULT 0,
                section_count INTEGER DEFAULT 0,
                keywords_json LONGTEXT NOT NULL,
                metadata_json LONGTEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.sections_table} (
                section_id VARCHAR(64) PRIMARY KEY,
                doc_id VARCHAR(64) NOT NULL,
                title VARCHAR(255) NULL,
                section_type VARCHAR(64) NULL,
                summary TEXT NULL,
                chunk_count INTEGER DEFAULT 0
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.chunks_table} (
                chunk_id VARCHAR(64) PRIMARY KEY,
                doc_id VARCHAR(64) NOT NULL,
                section_id VARCHAR(64) NULL,
                section_title VARCHAR(255) NULL,
                chunk_index INTEGER NULL,
                chunk_title VARCHAR(255) NULL,
                chunk_kind VARCHAR(40) NULL,
                preview TEXT NULL,
                text LONGTEXT NULL,
                page_start INTEGER NULL,
                page_end INTEGER NULL,
                risk_flag INTEGER DEFAULT 0,
                section_type VARCHAR(64) NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.pages_table} (
                doc_id VARCHAR(64) NOT NULL,
                page_number INTEGER NOT NULL,
                char_start INTEGER DEFAULT 0,
                char_end INTEGER DEFAULT 0,
                preview TEXT NULL,
                PRIMARY KEY (doc_id, page_number)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.entities_table} (
                doc_id VARCHAR(64) NOT NULL,
                chunk_id VARCHAR(64) NULL,
                entity_type VARCHAR(40) NOT NULL,
                entity_name VARCHAR(255) NOT NULL,
                normalized_name VARCHAR(255) NOT NULL,
                weight REAL DEFAULT 1.0
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.relations_table} (
                doc_id VARCHAR(64) NOT NULL,
                subject_name VARCHAR(255) NOT NULL,
                relation_type VARCHAR(64) NOT NULL,
                object_name VARCHAR(255) NOT NULL,
                weight REAL DEFAULT 1.0
            )
            """,
        ]
        for statement in statements:
            self.db.execute(statement)
        self.db.ensure_column(self.chunks_table, "section_type", "VARCHAR(64)")
        self.db.ensure_column(self.chunks_table, "page_start", "INTEGER")
        self.db.ensure_column(self.chunks_table, "page_end", "INTEGER")
        self.db.ensure_column(self.chunks_table, "chunk_kind", "VARCHAR(40)")
        self.db._ensure_index("idx_fin_documents_ticker", self.documents_table, "ticker")
        self.db._ensure_index("idx_fin_documents_company", self.documents_table, "company_name")
        self.db._ensure_index("idx_fin_documents_industry", self.documents_table, "industry")
        self.db._ensure_index("idx_fin_sections_doc_id", self.sections_table, "doc_id")
        self.db._ensure_index("idx_fin_chunks_doc_id", self.chunks_table, "doc_id")
        self.db._ensure_index("idx_fin_pages_doc_id", self.pages_table, "doc_id")
        self.db._ensure_index("idx_fin_entities_doc_id", self.entities_table, "doc_id")

    def stats(self) -> dict[str, Any]:
        return {
            "documents": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.documents_table}", default=0) or 0),
            "sections": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.sections_table}", default=0) or 0),
            "chunks": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.chunks_table}", default=0) or 0),
            "pages": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.pages_table}", default=0) or 0),
            "entities": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.entities_table}", default=0) or 0),
            "relations": int(self.db.scalar(f"SELECT COUNT(*) AS count FROM {self.relations_table}", default=0) or 0),
        }

    def upsert_document(self, detail: dict[str, Any]) -> None:
        metadata = self._extract_metadata(detail)
        section_type_map = {
            section["section_id"]: self._infer_section_type(section.get("title", ""))
            for section in detail.get("sections", [])
        }
        document_payload = {
            "doc_id": detail["doc_id"],
            "title": detail["title"],
            "filename": detail["filename"],
            "category": detail.get("category"),
            "doc_type": metadata["doc_type"],
            "company_name": metadata["company_name"],
            "ticker": metadata["ticker"],
            "industry": metadata["industry"],
            "publish_date": metadata["publish_date"],
            "report_period": metadata["report_period"],
            "summary": detail.get("summary", ""),
            "uploaded_at": detail.get("uploaded_at"),
            "chunk_count": int(detail.get("chunk_count", 0)),
            "section_count": int(detail.get("section_count", 0)),
            "keywords_json": json.dumps(detail.get("keywords", []), ensure_ascii=False),
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        }
        self.db.upsert(self.documents_table, document_payload, conflict_keys=["doc_id"])
        self.db.execute(f"DELETE FROM {self.sections_table} WHERE doc_id = %(doc_id)s", {"doc_id": detail["doc_id"]})
        self.db.execute(f"DELETE FROM {self.chunks_table} WHERE doc_id = %(doc_id)s", {"doc_id": detail["doc_id"]})
        self.db.execute(f"DELETE FROM {self.pages_table} WHERE doc_id = %(doc_id)s", {"doc_id": detail["doc_id"]})
        self.db.execute(f"DELETE FROM {self.entities_table} WHERE doc_id = %(doc_id)s", {"doc_id": detail["doc_id"]})
        self.db.execute(f"DELETE FROM {self.relations_table} WHERE doc_id = %(doc_id)s", {"doc_id": detail["doc_id"]})

        for section in detail.get("sections", []):
            section_type = section_type_map.get(section["section_id"], "general")
            self.db.execute(
                f"""
                INSERT INTO {self.sections_table} (section_id, doc_id, title, section_type, summary, chunk_count)
                VALUES (%(section_id)s, %(doc_id)s, %(title)s, %(section_type)s, %(summary)s, %(chunk_count)s)
                """,
                {
                    "section_id": section["section_id"],
                    "doc_id": detail["doc_id"],
                    "title": section.get("title", ""),
                    "section_type": section_type,
                    "summary": section.get("summary", ""),
                    "chunk_count": int(section.get("chunk_count", 0)),
                },
            )

        for page in detail.get("pages", []):
            self.db.execute(
                f"""
                INSERT INTO {self.pages_table} (doc_id, page_number, char_start, char_end, preview)
                VALUES (%(doc_id)s, %(page_number)s, %(char_start)s, %(char_end)s, %(preview)s)
                """,
                {
                    "doc_id": detail["doc_id"],
                    "page_number": int(page.get("page_number", 0)),
                    "char_start": int(page.get("char_start", 0)),
                    "char_end": int(page.get("char_end", 0)),
                    "preview": page.get("preview", ""),
                },
            )

        for chunk in detail.get("chunks", []):
            section_type = section_type_map.get(chunk.get("section_id"), "general")
            risk_flag = 1 if any(term in chunk.get("text", "") for term in RISK_TERMS) else 0
            self.db.execute(
                f"""
                INSERT INTO {self.chunks_table} (
                    chunk_id, doc_id, section_id, section_title, chunk_index, chunk_title,
                    chunk_kind, preview, text, page_start, page_end, risk_flag, section_type
                ) VALUES (
                    %(chunk_id)s, %(doc_id)s, %(section_id)s, %(section_title)s, %(chunk_index)s, %(chunk_title)s,
                    %(chunk_kind)s, %(preview)s, %(text)s, %(page_start)s, %(page_end)s, %(risk_flag)s, %(section_type)s
                )
                """,
                {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": detail["doc_id"],
                    "section_id": chunk.get("section_id"),
                    "section_title": chunk.get("section_title"),
                    "chunk_index": int(chunk.get("chunk_index", 0)),
                    "chunk_title": chunk.get("chunk_title", ""),
                    "chunk_kind": chunk.get("chunk_kind", "text"),
                    "preview": chunk.get("preview", ""),
                    "text": chunk.get("text", ""),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "risk_flag": risk_flag,
                    "section_type": section_type,
                },
            )
            for entity in self._extract_chunk_entities(detail, chunk):
                self.db.execute(
                    f"""
                    INSERT INTO {self.entities_table} (doc_id, chunk_id, entity_type, entity_name, normalized_name, weight)
                    VALUES (%(doc_id)s, %(chunk_id)s, %(entity_type)s, %(entity_name)s, %(normalized_name)s, %(weight)s)
                    """,
                    {
                        "doc_id": detail["doc_id"],
                        "chunk_id": chunk["chunk_id"],
                        "entity_type": entity["entity_type"],
                        "entity_name": entity["entity_name"],
                        "normalized_name": entity["normalized_name"],
                        "weight": entity["weight"],
                    },
                )

        for relation in self._extract_relations(metadata):
            self.db.execute(
                f"""
                INSERT INTO {self.relations_table} (doc_id, subject_name, relation_type, object_name, weight)
                VALUES (%(doc_id)s, %(subject_name)s, %(relation_type)s, %(object_name)s, %(weight)s)
                """,
                {
                    "doc_id": detail["doc_id"],
                    "subject_name": relation["subject_name"],
                    "relation_type": relation["relation_type"],
                    "object_name": relation["object_name"],
                    "weight": relation["weight"],
                },
            )

    def list_documents(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.fetchall(
            f"""
            SELECT doc_id, title, filename, category, doc_type, company_name, ticker, industry,
                   publish_date, report_period, summary, uploaded_at, chunk_count, section_count
            FROM {self.documents_table}
            ORDER BY uploaded_at DESC
            LIMIT %(limit)s
            """,
            {"limit": limit},
        )
        return rows

    def search_documents(
        self,
        query: str,
        *,
        company: str | None = None,
        ticker: str | None = None,
        sector: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        terms = [item for item in self._split_terms(query) if item]
        rows = self.db.fetchall(
            f"""
            SELECT doc_id, title, filename, category, doc_type, company_name, ticker, industry,
                   publish_date, report_period, summary, uploaded_at, chunk_count, section_count, keywords_json
            FROM {self.documents_table}
            """
        )

        ranked: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            text = " ".join(
                [
                    item.get("title") or "",
                    item.get("filename") or "",
                    item.get("summary") or "",
                    item.get("company_name") or "",
                    item.get("ticker") or "",
                    item.get("industry") or "",
                    item.get("doc_type") or "",
                    " ".join(json.loads(item.get("keywords_json") or "[]")),
                ]
            ).lower()
            score = 0.0
            for term in terms:
                if term.lower() in text:
                    score += 1.0
            if company and item.get("company_name") and company in item["company_name"]:
                score += 3.0
            if ticker and item.get("ticker") == ticker:
                score += 4.0
            if sector and item.get("industry") and sector.lower() in item["industry"].lower():
                score += 2.0
            if item.get("doc_type") in {"annual_report", "quarterly_report"}:
                score += 0.2
            if score <= 0:
                continue
            item["meta_score"] = score
            ranked.append(item)

        ranked.sort(key=lambda value: (value["meta_score"], value.get("uploaded_at") or ""), reverse=True)
        return ranked[:limit]

    def search_chunk_candidates(
        self,
        query: str,
        *,
        task_type: str,
        doc_ids: list[str],
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        if not doc_ids:
            return []
        terms = [item.lower() for item in self._split_terms(query)]
        where_clause, params = self._build_in_clause("doc_id", doc_ids, "doc_id")
        rows = self.db.fetchall(
            f"""
            SELECT chunk_id, doc_id, section_id, section_title, chunk_title, preview, text, risk_flag, section_type,
                   chunk_kind, page_start, page_end
            FROM {self.chunks_table}
            WHERE {where_clause}
            """,
            params,
        )
        priorities = TASK_SECTION_PRIORITIES.get(task_type, {})
        ranked: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            text = " ".join(
                [
                    item.get("section_title") or "",
                    item.get("chunk_title") or "",
                    item.get("preview") or "",
                    item.get("text") or "",
                ]
            ).lower()
            score = 0.0
            for term in terms:
                if term in text:
                    score += 1.0
            score *= priorities.get(item.get("section_type") or "general", 1.0)
            if item.get("risk_flag"):
                score += 0.2
            if score <= 0:
                continue
            item["meta_score"] = score
            ranked.append(item)
        ranked.sort(key=lambda value: value["meta_score"], reverse=True)
        return ranked[:limit]

    def get_chunk_metadata_map(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        where_clause, params = self._build_in_clause("chunks.chunk_id", chunk_ids, "chunk_id")
        rows = self.db.fetchall(
            f"""
            SELECT
                chunks.chunk_id,
                chunks.section_id,
                chunks.section_title,
                chunks.section_type,
                chunks.chunk_kind,
                chunks.page_start,
                chunks.page_end,
                documents.doc_type,
                documents.company_name,
                documents.ticker,
                documents.industry,
                documents.publish_date,
                documents.report_period
            FROM {self.chunks_table} AS chunks
            JOIN {self.documents_table} AS documents ON documents.doc_id = chunks.doc_id
            WHERE {where_clause}
            """,
            params,
        )
        return {row["chunk_id"]: dict(row) for row in rows}

    def _extract_metadata(self, detail: dict[str, Any]) -> dict[str, Any]:
        title = detail.get("title", "")
        filename = detail.get("filename", "")
        probe = f"{title}\n{filename}\n{detail.get('summary', '')}"
        doc_type = self._guess_doc_type(probe)
        company_name = self._guess_company_name(probe)
        ticker = self._guess_ticker(probe)
        industry = self._guess_industry(probe, detail.get("keywords", []))
        publish_date = self._guess_date(probe)
        report_period = self._guess_report_period(probe)
        return {
            "doc_type": doc_type,
            "company_name": company_name,
            "ticker": ticker,
            "industry": industry,
            "publish_date": publish_date,
            "report_period": report_period,
        }

    def _extract_chunk_entities(self, detail: dict[str, Any], chunk: dict[str, Any]) -> list[dict[str, Any]]:
        text = f"{detail.get('title', '')}\n{chunk.get('chunk_title', '')}\n{chunk.get('text', '')}"
        entities: list[dict[str, Any]] = []
        company = self._guess_company_name(text)
        if company:
            entities.append(
                {
                    "entity_type": "company",
                    "entity_name": company,
                    "normalized_name": company.lower(),
                    "weight": 1.0,
                }
            )
        ticker = self._guess_ticker(text)
        if ticker:
            entities.append(
                {
                    "entity_type": "ticker",
                    "entity_name": ticker,
                    "normalized_name": ticker,
                    "weight": 1.0,
                }
            )
        for industry in INDUSTRY_TERMS:
            if industry.lower() in text.lower():
                entities.append(
                    {
                        "entity_type": "industry",
                        "entity_name": industry,
                        "normalized_name": industry.lower(),
                        "weight": 0.8,
                    }
                )
        return entities[:6]

    def _extract_relations(self, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        company = metadata.get("company_name")
        ticker = metadata.get("ticker")
        industry = metadata.get("industry")
        doc_type = metadata.get("doc_type")
        if company and ticker:
            relations.append(
                {
                    "subject_name": company,
                    "relation_type": "has_ticker",
                    "object_name": ticker,
                    "weight": 1.0,
                }
            )
        if company and industry:
            relations.append(
                {
                    "subject_name": company,
                    "relation_type": "belongs_to_industry",
                    "object_name": industry,
                    "weight": 0.9,
                }
            )
        if company and doc_type:
            relations.append(
                {
                    "subject_name": company,
                    "relation_type": "has_document_type",
                    "object_name": doc_type,
                    "weight": 0.6,
                }
            )
        return relations

    def _guess_doc_type(self, probe: str) -> str:
        lowered = probe.lower()
        for doc_type, terms in REPORT_TERMS.items():
            if any(term.lower() in lowered for term in terms):
                return doc_type
        return "upload"

    def _guess_company_name(self, probe: str) -> str | None:
        suffix_pattern = "|".join(COMPANY_SUFFIXES)
        match = re.search(rf"([\u4e00-\u9fff]{{2,16}}(?:{suffix_pattern}))", probe)
        if match:
            return match.group(1)
        return None

    def _guess_ticker(self, probe: str) -> str | None:
        match = re.search(r"\b([036]\d{5})\b", probe)
        return match.group(1) if match else None

    def _guess_industry(self, probe: str, keywords: list[str]) -> str | None:
        lowered = probe.lower()
        for item in [*INDUSTRY_TERMS, *keywords]:
            if str(item).lower() in lowered:
                return str(item)
        return None

    def _guess_date(self, probe: str) -> str | None:
        match = re.search(
            r"(20\d{2}(?:[-/\u5e74])(?:0?[1-9]|1[0-2])(?:(?:[-/\u6708])(?:0?[1-9]|[12]\d|3[01]))?)",
            probe,
        )
        return match.group(1) if match else None

    def _guess_report_period(self, probe: str) -> str | None:
        for marker in ("\u4e00\u5b63\u5ea6", "\u534a\u5e74", "\u4e09\u5b63\u5ea6", "\u5168\u5e74"):
            if marker in probe:
                return marker
        return None

    def _infer_section_type(self, title: str) -> str:
        lowered = title.lower()
        for section_type, terms in SECTION_TYPE_RULES.items():
            if any(term.lower() in lowered for term in terms):
                return section_type
        return "general"

    def _split_terms(self, query: str) -> list[str]:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", query)
        return [item for item in normalized.split() if len(item) >= 2]
