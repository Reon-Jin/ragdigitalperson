from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings
from app.rag.background import BackgroundTaskManager
from app.rag.chunking import Chunker
from app.rag.embeddings import EmbeddingService
from app.rag.ingestion import IngestionService
from app.rag.parsers import DocumentParser
from app.rag.repositories import RAGRepository
from app.rag.reranker import RerankerService
from app.rag.search import SearchService
from app.rag.vector_store import VectorStore


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = RAGRepository(settings)
        self.parser = DocumentParser(settings)
        self.chunker = Chunker(settings)
        self.embedding_service = EmbeddingService(settings)
        self.reranker = RerankerService(settings)
        self.vector_store = VectorStore(settings)
        self.ingestion_service = IngestionService(settings, self.repository, self.parser, self.chunker, self.embedding_service, self.vector_store)
        self.search_service = SearchService(settings, self.repository, self.embedding_service, self.reranker, self.vector_store)
        self.background = BackgroundTaskManager(settings)

    def queue_upload(self, *, temp_path: Path, filename: str, user_id: str) -> dict:
        suffix = temp_path.suffix.lower()
        if suffix not in {".txt", ".md", ".pdf", ".docx"}:
            raise ValueError(f"Unsupported file type: {suffix}")
        doc = self.repository.create_document(
            user_id=user_id,
            filename=filename,
            stored_path="",
            suffix=suffix,
            file_size=temp_path.stat().st_size,
        )
        final_path = self.resolve_storage_path(doc["doc_id"], suffix, user_id)
        shutil.move(str(temp_path), final_path)
        self.repository.db.execute(
            "UPDATE documents SET stored_path = %(stored_path)s WHERE doc_id = %(doc_id)s",
            {"stored_path": str(final_path), "doc_id": doc["doc_id"]},
        )
        job = self.repository.create_job(doc_id=doc["doc_id"], user_id=user_id, filename=filename)
        self.background.submit(job_id=job["job_id"], doc_id=doc["doc_id"])
        return {"doc": self.repository.get_document(doc["doc_id"], user_id=user_id), "job": self.repository.get_job(job["job_id"], user_id=user_id)}

    def resolve_storage_path(self, doc_id: str, suffix: str, user_id: str) -> Path:
        user_dir = self.settings.uploads_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir / f"{doc_id}{suffix}"

    def get_job(self, job_id: str, user_id: str) -> dict | None:
        return self.repository.get_job(job_id, user_id=user_id)

    def list_documents(self, user_id: str) -> list[dict]:
        return self.repository.list_documents(user_id=user_id)

    def get_document(self, doc_id: str, user_id: str) -> dict | None:
        doc = self.repository.get_document(doc_id, user_id=user_id)
        if not doc:
            return None
        chunks = self.repository.list_chunks(doc_id=doc_id, user_id=user_id)
        sections: dict[str, list[dict]] = {}
        for chunk in chunks:
            sections.setdefault(chunk["section_title"] or "文档", []).append(chunk)
        doc["sections"] = [
            {
                "section_id": f"{doc_id}:{index}",
                "doc_id": doc_id,
                "title": title,
                "order": index,
                "summary": items[0]["preview"] if items else "",
                "chunk_count": len(items),
                "previews": [
                    {
                        "chunk_id": item["chunk_id"],
                        "chunk_index": item["chunk_index"],
                        "chunk_title": item["section_title"] or f"Chunk {item['chunk_index'] + 1}",
                        "chunk_kind": item["chunk_kind"],
                        "section_id": f"{doc_id}:{index}",
                        "section_title": title,
                        "preview": item["preview"],
                        "word_count": item["token_count"],
                        "page_start": item["page_start"],
                        "page_end": item["page_end"],
                    }
                    for item in items[:3]
                ],
            }
            for index, (title, items) in enumerate(sections.items())
        ]
        doc["chunks"] = [
            {
                "chunk_id": item["chunk_id"],
                "chunk_index": item["chunk_index"],
                "chunk_title": item["section_title"] or f"Chunk {item['chunk_index'] + 1}",
                "section_id": f"{doc_id}:{index}",
                "section_title": item["section_title"],
                "text": item["text"],
                "preview": item["preview"],
                "chunk_kind": item["chunk_kind"],
                "word_count": item["token_count"],
                "char_start": item["char_start"],
                "char_end": item["char_end"],
                "page_start": item["page_start"],
                "page_end": item["page_end"],
            }
            for index, item in enumerate(chunks)
        ]
        doc["pages"] = []
        return doc

    def delete_document(self, doc_id: str, user_id: str) -> bool:
        deleted = self.repository.delete_document(doc_id, user_id=user_id)
        if deleted:
            self.vector_store.delete_by_doc_id(doc_id)
        return deleted

    def search(self, query: str, *, user_id: str, doc_id: str | None = None) -> list[dict]:
        hits = self.search_service.search(query, user_id=user_id, doc_id=doc_id)
        return [
            {
                "doc_id": hit.doc_id,
                "filename": hit.filename,
                "category": hit.category,
                "title": hit.title,
                "section_id": f"{hit.doc_id}:{hit.chunk_index}",
                "section_title": hit.section_title,
                "chunk_id": hit.chunk_id,
                "chunk_index": hit.chunk_index,
                "chunk_title": hit.chunk_title,
                "score": round(hit.score, 4),
                "text": hit.text,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "chunk_kind": hit.chunk_kind,
                "metadata": hit.metadata,
            }
            for hit in hits
        ]


@lru_cache(maxsize=1)
def build_rag_service() -> RAGService:
    return RAGService(get_settings())
