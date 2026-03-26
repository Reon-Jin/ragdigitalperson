from __future__ import annotations

import re
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
        self.ingestion_service = IngestionService(
            settings,
            self.repository,
            self.parser,
            self.chunker,
            self.embedding_service,
            self.vector_store,
        )
        self.search_service = SearchService(
            settings,
            self.repository,
            self.embedding_service,
            self.reranker,
            self.vector_store,
        )
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
        return {
            "doc": self.repository.get_document(doc["doc_id"], user_id=user_id),
            "job": self.repository.get_job(job["job_id"], user_id=user_id),
        }

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

        chunks = self._dedupe_chunks(self.repository.list_chunks(doc_id=doc_id, user_id=user_id))
        sections: dict[str, list[dict]] = {}
        for chunk in chunks:
            sections.setdefault(chunk["section_title"] or "文档", []).append(chunk)

        section_ids = {title: f"{doc_id}:{index}" for index, title in enumerate(sections.keys())}
        headings = [title for title in sections.keys() if title and title != "文档"]

        doc["sections"] = [
            {
                "section_id": section_ids[title],
                "doc_id": doc_id,
                "title": title,
                "order": index,
                "summary": items[0]["preview"] if items else "",
                "chunk_count": len(items),
                "previews": [
                    {
                        "chunk_id": item["chunk_id"],
                        "chunk_index": item["chunk_index"],
                        "chunk_title": self._chunk_title(item),
                        "chunk_kind": item["chunk_kind"],
                        "section_id": section_ids[title],
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
                "chunk_title": self._chunk_title(item),
                "section_id": section_ids.get(item["section_title"] or "文档", f"{doc_id}:0"),
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
            for item in chunks
        ]

        doc["pages"] = self._build_pages(doc_id, doc["chunks"])
        doc["chunk_count"] = len(doc["chunks"])
        doc["section_count"] = len(doc["sections"])
        doc["headings"] = headings[:20]
        if doc["chunks"] and not doc.get("summary"):
            doc["summary"] = doc["chunks"][0]["preview"]
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

    def _build_pages(self, doc_id: str, chunks: list[dict]) -> list[dict]:
        pages: dict[int, dict] = {}
        for chunk in chunks:
            page_start = int(chunk.get("page_start") or 0)
            page_end = int(chunk.get("page_end") or page_start or 0)
            if page_start <= 0:
                continue
            for page_number in range(page_start, max(page_start, page_end) + 1):
                page = pages.setdefault(
                    page_number,
                    {
                        "doc_id": doc_id,
                        "page_number": page_number,
                        "char_start": 0,
                        "char_end": 0,
                        "preview": "",
                        "text": "",
                        "chunks": [],
                    },
                )
                page["chunks"].append(
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
                )

        for page in pages.values():
            page_text = "\n\n".join(item["preview"] for item in page["chunks"][:8] if item.get("preview"))
            page["preview"] = page["chunks"][0]["preview"] if page["chunks"] else ""
            page["text"] = page_text
            page["char_end"] = len(page_text)
        return [pages[number] for number in sorted(pages.keys())]

    def _dedupe_chunks(self, chunks: list[dict]) -> list[dict]:
        seen: set[str] = set()
        deduped: list[dict] = []
        for item in chunks:
            signature = " ".join(str(item.get("text", "")).split()).strip().lower()[:220]
            if not signature or signature in seen:
                continue
            seen.add(signature)
            deduped.append(item)
        return deduped

    def _chunk_title(self, item: dict) -> str:
        preview = re.sub(r"\s+", " ", str(item.get("preview", "")).strip())
        if preview:
            return preview[:30]
        section_title = str(item.get("section_title", "")).strip()
        if section_title:
            return section_title[:30]
        return f"Chunk {int(item.get('chunk_index', 0)) + 1}"


@lru_cache(maxsize=1)
def build_rag_service() -> RAGService:
    return RAGService(get_settings())
