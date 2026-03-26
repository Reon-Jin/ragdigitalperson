from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.config import Settings
from app.rag.service import RAGService, build_rag_service


SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}


@dataclass
class SearchResult:
    doc_id: str
    filename: str
    category: str
    title: str
    section_id: str
    section_title: str
    chunk_id: str
    chunk_index: int
    chunk_title: str
    page_start: int | None
    page_end: int | None
    chunk_kind: str
    score: float
    text: str


class DocumentStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rag: RAGService = build_rag_service()
        self.db = self.rag.repository.db
        self._refresh_state()

    def _refresh_state(self) -> None:
        self.docs = self.rag.repository.list_documents()
        self.chunks = self.rag.repository.list_chunks()
        self.sections: list[dict[str, Any]] = []
        self.pages: list[dict[str, Any]] = []

    def user_upload_dir(self, user_id: str) -> Path:
        path = self.settings.uploads_dir / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_storage_path(self, doc_id: str, suffix: str, user_id: str) -> Path:
        return self.rag.resolve_storage_path(doc_id, suffix, user_id)

    def list_files(self, user_id: str | None = None) -> list[dict[str, Any]]:
        files = self.rag.list_documents(user_id or "")
        self._refresh_state()
        return [
            {
                "doc_id": item["doc_id"],
                "filename": item["filename"],
                "category": item.get("category") or "未分类",
                "title": item["title"],
                "suffix": item["suffix"],
                "uploaded_at": item["uploaded_at"],
                "chunk_count": int(item.get("chunk_count") or 0),
                "section_count": int(item.get("section_count") or 0),
                "summary": item.get("summary") or "",
                "keywords": item.get("keywords") or [],
                "status": item.get("status") or "queued",
            }
            for item in files
        ]

    def get_catalog(self, user_id: str | None = None) -> list[dict[str, Any]]:
        catalog = []
        for item in self.list_files(user_id=user_id):
            detail = self.get_document(item["doc_id"], user_id=user_id)
            if detail:
                catalog.append(
                    {
                        "doc_id": item["doc_id"],
                        "filename": item["filename"],
                        "category": item["category"],
                        "title": item["title"],
                        "summary": item["summary"],
                        "keywords": item["keywords"],
                        "chunks": [
                            {
                                "chunk_id": chunk["chunk_id"],
                                "chunk_title": chunk["chunk_title"],
                                "chunk_kind": chunk["chunk_kind"],
                                "section_id": chunk["section_id"],
                                "section_title": chunk["section_title"],
                                "chunk_index": chunk["chunk_index"],
                                "preview": chunk["preview"],
                                "page_start": chunk.get("page_start"),
                                "page_end": chunk.get("page_end"),
                            }
                            for chunk in detail["chunks"][:8]
                        ],
                    }
                )
        return catalog

    def get_document(self, doc_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        detail = self.rag.get_document(doc_id, user_id or "")
        self._refresh_state()
        return detail

    def get_section(self, doc_id: str, section_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        detail = self.get_document(doc_id, user_id=user_id)
        if not detail:
            return None
        for section in detail["sections"]:
            if section["section_id"] == section_id:
                chunks = [chunk for chunk in detail["chunks"] if chunk["section_title"] == section["title"]]
                return {**section, "chunks": chunks}
        return None

    def get_page(self, doc_id: str, page_number: int, user_id: str | None = None) -> dict[str, Any] | None:
        detail = self.get_document(doc_id, user_id=user_id)
        if not detail:
            return None
        chunks = [
            {
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "chunk_title": chunk["chunk_title"],
                "chunk_kind": chunk["chunk_kind"],
                "section_id": chunk["section_id"],
                "section_title": chunk["section_title"],
                "preview": chunk["preview"],
                "word_count": chunk["word_count"],
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
            }
            for chunk in detail["chunks"]
            if (chunk.get("page_start") or 0) <= page_number <= (chunk.get("page_end") or chunk.get("page_start") or 0)
        ]
        return {
            "doc_id": doc_id,
            "page_number": page_number,
            "char_start": 0,
            "char_end": 0,
            "preview": chunks[0]["preview"] if chunks else "",
            "text": "",
            "chunks": chunks,
        }

    def delete_document(self, doc_id: str, user_id: str | None = None) -> bool:
        deleted = self.rag.delete_document(doc_id, user_id or "")
        self._refresh_state()
        return deleted

    def update_document_title(self, doc_id: str, title: str) -> dict[str, Any] | None:
        self.db.execute("UPDATE documents SET title = %(title)s WHERE doc_id = %(doc_id)s", {"title": title, "doc_id": doc_id})
        self._refresh_state()
        return self.get_document(doc_id)

    def update_chunk_title(self, doc_id: str, chunk_id: str, chunk_title: str) -> dict[str, Any] | None:
        self.db.execute("UPDATE chunk_metadata SET section_title = %(section_title)s WHERE chunk_id = %(chunk_id)s AND doc_id = %(doc_id)s", {"section_title": chunk_title, "chunk_id": chunk_id, "doc_id": doc_id})
        detail = self.get_document(doc_id)
        if not detail:
            return None
        for chunk in detail["chunks"]:
            if chunk["chunk_id"] == chunk_id:
                return {
                    "chunk_id": chunk["chunk_id"],
                    "chunk_index": chunk["chunk_index"],
                    "chunk_title": chunk["chunk_title"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "preview": chunk["preview"],
                    "word_count": chunk["word_count"],
                }
        return None

    def rank_documents(self, queries: Sequence[str], *, categories: Sequence[str] | None = None, user_id: str | None = None, limit: int = 12) -> list[dict[str, Any]]:
        docs = self.list_files(user_id=user_id)
        if categories:
            allowed = set(categories)
            docs = [item for item in docs if item["category"] in allowed]
        scored: dict[str, float] = {item["doc_id"]: 0.0 for item in docs}
        for query in queries:
            results = self.rag.search(query, user_id=user_id or "")
            for index, item in enumerate(results):
                scored[item["doc_id"]] = max(scored.get(item["doc_id"], 0.0), float(item["score"]) + max(0.0, 0.2 - index * 0.01))
        ranked = sorted(docs, key=lambda item: scored.get(item["doc_id"], 0.0), reverse=True)
        return [dict(item, score=round(scored.get(item["doc_id"], 0.0), 4)) for item in ranked[:limit]]

    def rank_chunks(self, queries: Sequence[str], *, categories: Sequence[str] | None = None, doc_ids: Sequence[str] | None = None, chunk_ids: Sequence[str] | None = None, user_id: str | None = None, limit: int = 20) -> list[SearchResult]:
        aggregated: dict[str, SearchResult] = {}
        target_doc_ids = list(doc_ids or [])
        for query in queries:
            doc_scope = target_doc_ids if target_doc_ids else [None]
            for scoped_doc_id in doc_scope:
                results = self.rag.search(query, user_id=user_id or "", doc_id=scoped_doc_id)
                for item in results:
                    existing = aggregated.get(item["chunk_id"])
                    candidate = SearchResult(
                        doc_id=item["doc_id"],
                        filename=item["filename"],
                        category=item["category"],
                        title=item["title"],
                        section_id=item["section_id"],
                        section_title=item["section_title"],
                        chunk_id=item["chunk_id"],
                        chunk_index=item["chunk_index"],
                        chunk_title=item["chunk_title"],
                        page_start=item.get("page_start"),
                        page_end=item.get("page_end"),
                        chunk_kind=item["chunk_kind"],
                        score=item["score"],
                        text=item["text"],
                    )
                    if existing is None or candidate.score > existing.score:
                        aggregated[candidate.chunk_id] = candidate
        hits = list(aggregated.values())
        if chunk_ids:
            allowed = set(chunk_ids)
            hits = [item for item in hits if item.chunk_id in allowed]
        if categories:
            allowed = set(categories)
            hits = [item for item in hits if item.category in allowed]
        if doc_ids:
            allowed_doc_ids = set(doc_ids)
            hits = [item for item in hits if item.doc_id in allowed_doc_ids]
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:limit]

    def hierarchical_search(self, queries: Sequence[str], *, categories: Sequence[str] | None = None, doc_ids: Sequence[str] | None = None, chunk_ids: Sequence[str] | None = None, user_id: str | None = None) -> tuple[list[SearchResult], list[dict[str, Any]]]:
        hits = self.rank_chunks(queries, categories=categories, doc_ids=doc_ids, chunk_ids=chunk_ids, user_id=user_id, limit=self.settings.answer_top_k)
        trace = [
            {
                "id": item.chunk_id,
                "label": item.chunk_title,
                "score": item.score,
                "level": "chunk",
                "parent_id": item.doc_id,
            }
            for item in hits
        ]
        return hits, trace

    def get_chunks_by_ids(self, chunk_ids: Sequence[str]) -> list[SearchResult]:
        chunk_map = self.rag.repository.get_chunk_map(list(chunk_ids))
        doc_map = {item["doc_id"]: item for item in self.rag.repository.list_documents()}
        results = []
        for chunk_id in chunk_ids:
            item = chunk_map.get(chunk_id)
            if not item:
                continue
            doc = doc_map.get(item["doc_id"], {})
            results.append(
                SearchResult(
                    doc_id=item["doc_id"],
                    filename=item["filename"],
                    category=doc.get("category", "未分类"),
                    title=doc.get("title", item["filename"]),
                    section_id=f"{item['doc_id']}:{item['chunk_index']}",
                    section_title=item["section_title"],
                    chunk_id=item["chunk_id"],
                    chunk_index=item["chunk_index"],
                    chunk_title=item["section_title"] or f"Chunk {item['chunk_index'] + 1}",
                    page_start=item.get("page_start"),
                    page_end=item.get("page_end"),
                    chunk_kind=item["chunk_kind"],
                    score=1.0,
                    text=item["text"],
                )
            )
        return results

    def search(self, query: str, top_k: int | None = None) -> list[SearchResult]:
        return self.rank_chunks([query], limit=top_k or self.settings.answer_top_k)

    def _extract_original_name(self, temp_path: Path) -> str:
        name = temp_path.name
        return name.split("--", 1)[1] if "--" in name else name
