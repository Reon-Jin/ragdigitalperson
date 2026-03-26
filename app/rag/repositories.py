from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.rag.types import ChunkRecord, SearchHit
from app.storage.database import Database


class RAGRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()

    def create_document(self, *, user_id: str, filename: str, stored_path: str, suffix: str, file_size: int, source_type: str = "upload") -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "doc_id": str(uuid.uuid4()),
            "user_id": user_id,
            "filename": filename,
            "stored_path": stored_path,
            "category": "未分类",
            "title": Path(filename).stem,
            "suffix": suffix,
            "uploaded_at": now,
            "status": "queued",
            "source_type": source_type,
            "file_size": file_size,
            "chunk_count": 0,
            "section_count": 0,
            "page_count": 0,
            "summary": "",
            "headings_json": "[]",
            "keywords_json": "[]",
            "embedding_json": "[]",
        }
        self.db.execute(
            """
            INSERT INTO documents (
                doc_id, user_id, filename, stored_path, category, title, suffix, uploaded_at, status,
                source_type, file_size, chunk_count, section_count, page_count, summary, headings_json,
                keywords_json, embedding_json
            ) VALUES (
                %(doc_id)s, %(user_id)s, %(filename)s, %(stored_path)s, %(category)s, %(title)s, %(suffix)s,
                %(uploaded_at)s, %(status)s, %(source_type)s, %(file_size)s, %(chunk_count)s, %(section_count)s,
                %(page_count)s, %(summary)s, %(headings_json)s, %(keywords_json)s, %(embedding_json)s
            )
            """,
            payload,
        )
        return payload

    def create_job(self, *, doc_id: str, user_id: str, filename: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "job_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "user_id": user_id,
            "filename": filename,
            "status": "queued",
            "stage": "queued",
            "progress": 0.0,
            "message": "等待后台处理",
            "error_message": None,
            "retry_count": 0,
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.db.execute(
            """
            INSERT INTO ingestion_jobs (
                job_id, doc_id, user_id, filename, status, stage, progress, message, error_message,
                retry_count, started_at, completed_at, created_at, updated_at
            ) VALUES (
                %(job_id)s, %(doc_id)s, %(user_id)s, %(filename)s, %(status)s, %(stage)s, %(progress)s, %(message)s,
                %(error_message)s, %(retry_count)s, %(started_at)s, %(completed_at)s, %(created_at)s, %(updated_at)s
            )
            """,
            payload,
        )
        return payload

    def update_job(self, job_id: str, *, status: str, stage: str, progress: float, message: str = "", error_message: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            UPDATE ingestion_jobs
            SET status = %(status)s, stage = %(stage)s, progress = %(progress)s, message = %(message)s,
                error_message = %(error_message)s,
                started_at = COALESCE(started_at, %(started_at)s),
                completed_at = %(completed_at)s,
                updated_at = %(updated_at)s
            WHERE job_id = %(job_id)s
            """,
            {
                "job_id": job_id,
                "status": status,
                "stage": stage,
                "progress": progress,
                "message": message,
                "error_message": error_message,
                "started_at": now if status != "queued" else None,
                "completed_at": now if status in {"completed", "failed"} else None,
                "updated_at": now,
            },
        )

    def update_document_status(self, doc_id: str, *, status: str, title: str | None = None, summary: str | None = None, headings: list[str] | None = None, keywords: list[str] | None = None, chunk_count: int | None = None, section_count: int | None = None, page_count: int | None = None) -> None:
        current = self.get_document(doc_id)
        if not current:
            return
        payload = {
            "doc_id": doc_id,
            "status": status,
            "title": title if title is not None else current["title"],
            "summary": summary if summary is not None else current.get("summary", ""),
            "headings_json": json.dumps(headings if headings is not None else current.get("headings", []), ensure_ascii=False),
            "keywords_json": json.dumps(keywords if keywords is not None else current.get("keywords", []), ensure_ascii=False),
            "chunk_count": chunk_count if chunk_count is not None else current.get("chunk_count", 0),
            "section_count": section_count if section_count is not None else current.get("section_count", 0),
            "page_count": page_count if page_count is not None else current.get("page_count", 0),
        }
        self.db.execute(
            """
            UPDATE documents
            SET status = %(status)s, title = %(title)s, summary = %(summary)s, headings_json = %(headings_json)s,
                keywords_json = %(keywords_json)s, chunk_count = %(chunk_count)s, section_count = %(section_count)s,
                page_count = %(page_count)s
            WHERE doc_id = %(doc_id)s
            """,
            payload,
        )

    def replace_chunks(self, *, doc_id: str, user_id: str, chunks: list[ChunkRecord]) -> None:
        self.db.execute("DELETE FROM chunk_metadata WHERE doc_id = %(doc_id)s", {"doc_id": doc_id})
        items = [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "user_id": user_id,
                "filename": chunk.filename,
                "section_title": chunk.section_title,
                "chunk_index": chunk.chunk_index,
                "chunk_kind": chunk.chunk_kind,
                "source_type": chunk.source_type,
                "text": chunk.text,
                "preview": chunk.preview,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "token_count": chunk.token_count,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "created_at": chunk.created_at,
            }
            for chunk in chunks
        ]
        self.db.execute_many(
            """
            INSERT INTO chunk_metadata (
                chunk_id, doc_id, user_id, filename, section_title, chunk_index, chunk_kind, source_type,
                text, preview, page_start, page_end, token_count, char_start, char_end, created_at
            ) VALUES (
                %(chunk_id)s, %(doc_id)s, %(user_id)s, %(filename)s, %(section_title)s, %(chunk_index)s, %(chunk_kind)s,
                %(source_type)s, %(text)s, %(preview)s, %(page_start)s, %(page_end)s, %(token_count)s,
                %(char_start)s, %(char_end)s, %(created_at)s
            )
            """,
            items,
        )

    def get_job(self, job_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM ingestion_jobs WHERE job_id = %(job_id)s", {"job_id": job_id})
        if not row or (user_id and row["user_id"] != user_id):
            return None
        return row

    def get_document(self, doc_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        row = self.db.fetchone("SELECT * FROM documents WHERE doc_id = %(doc_id)s", {"doc_id": doc_id})
        if not row or (user_id and row["user_id"] != user_id):
            return None
        row["headings"] = json.loads(row.get("headings_json") or "[]")
        row["keywords"] = json.loads(row.get("keywords_json") or "[]")
        return row

    def list_documents(self, user_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.db.fetchall("SELECT * FROM documents ORDER BY uploaded_at DESC")
        documents = []
        for row in rows:
            if user_id and row["user_id"] != user_id:
                continue
            row["headings"] = json.loads(row.get("headings_json") or "[]")
            row["keywords"] = json.loads(row.get("keywords_json") or "[]")
            documents.append(row)
        return documents

    def list_chunks(self, *, doc_id: str | None = None, user_id: str | None = None) -> list[dict[str, Any]]:
        if doc_id:
            rows = self.db.fetchall("SELECT * FROM chunk_metadata WHERE doc_id = %(doc_id)s ORDER BY chunk_index ASC", {"doc_id": doc_id})
        else:
            rows = self.db.fetchall("SELECT * FROM chunk_metadata ORDER BY created_at DESC")
        return [row for row in rows if not user_id or row["user_id"] == user_id]

    def get_chunk_map(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        rows = self.db.fetchall("SELECT * FROM chunk_metadata ORDER BY created_at DESC")
        return {row["chunk_id"]: row for row in rows if row["chunk_id"] in set(chunk_ids)}

    def delete_document(self, doc_id: str, user_id: str | None = None) -> bool:
        doc = self.get_document(doc_id, user_id=user_id)
        if not doc:
            return False
        self.db.execute("DELETE FROM chunk_metadata WHERE doc_id = %(doc_id)s", {"doc_id": doc_id})
        self.db.execute("DELETE FROM ingestion_jobs WHERE doc_id = %(doc_id)s", {"doc_id": doc_id})
        self.db.execute("DELETE FROM documents WHERE doc_id = %(doc_id)s", {"doc_id": doc_id})
        stored_path = Path(str(doc.get("stored_path") or ""))
        if stored_path.exists():
            stored_path.unlink(missing_ok=True)
        return True

    def build_search_hits(self, rows: list[dict[str, Any]], scores: dict[str, float], documents: dict[str, dict[str, Any]]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for row in rows:
            doc = documents.get(row["doc_id"], {})
            hits.append(
                SearchHit(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    filename=row["filename"],
                    title=str(doc.get("title") or row["filename"]),
                    category=str(doc.get("category") or "未分类"),
                    section_title=row["section_title"],
                    chunk_index=int(row["chunk_index"]),
                    chunk_title=row["section_title"] or f"Chunk {int(row['chunk_index']) + 1}",
                    chunk_kind=row["chunk_kind"],
                    page_start=row.get("page_start"),
                    page_end=row.get("page_end"),
                    score=float(scores.get(row["chunk_id"], 0.0)),
                    text=row["text"],
                    metadata=row,
                )
            )
        return hits
