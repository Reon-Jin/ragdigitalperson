from __future__ import annotations

import logging
import time
from pathlib import Path

from qdrant_client.http import models as rest

from app.config import Settings
from app.rag.chunking import Chunker
from app.rag.embeddings import EmbeddingService
from app.rag.parsers import DocumentParser
from app.rag.repositories import RAGRepository
from app.rag.vector_store import VectorStore


logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, settings: Settings, repository: RAGRepository, parser: DocumentParser, chunker: Chunker, embedding_service: EmbeddingService, vector_store: VectorStore) -> None:
        self.settings = settings
        self.repository = repository
        self.parser = parser
        self.chunker = chunker
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def ingest_document(self, *, job_id: str, doc_id: str) -> None:
        doc = self.repository.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        started = time.perf_counter()
        try:
            self.repository.update_job(job_id, status="running", stage="extracting", progress=0.05, message="正在提取文档内容")
            self.repository.update_document_status(doc_id, status="processing")

            extracted = self.parser.parse(
                doc_id,
                file_path=Path(str(doc["stored_path"])),
                filename=doc["filename"],
                source_type=doc.get("source_type", "upload"),
            )
            self.repository.update_job(job_id, status="running", stage="chunking", progress=0.35, message="正在切分文档")
            chunks = self.chunker.chunk(extracted)
            if not chunks:
                raise RuntimeError("文档抽取后没有可用文本，无法生成分块。")
            headings = list(dict.fromkeys(chunk.section_title for chunk in chunks if chunk.section_title))[:24]
            summary = chunks[0].preview if chunks else ""
            self.repository.replace_chunks(doc_id=doc_id, user_id=doc["user_id"], chunks=chunks)

            self.repository.update_job(job_id, status="running", stage="embedding", progress=0.55, message="正在生成向量")
            vectors = self.embedding_service.encode_texts([chunk.text for chunk in chunks])

            self.repository.update_job(job_id, status="running", stage="indexing", progress=0.82, message="正在写入向量库")
            batch_size = max(1, self.settings.ingestion_batch_size)
            self.vector_store.delete_by_doc_id(doc_id)
            for start in range(0, len(chunks), batch_size):
                batch_chunks = chunks[start:start + batch_size]
                batch_vectors = vectors[start:start + batch_size]
                points = [
                    rest.PointStruct(
                        id=chunk.chunk_id,
                        vector=vector,
                        payload={
                            "chunk_id": chunk.chunk_id,
                            "doc_id": chunk.doc_id,
                            "user_id": doc["user_id"],
                            "filename": chunk.filename,
                            "section_title": chunk.section_title,
                            "chunk_index": chunk.chunk_index,
                            "chunk_kind": chunk.chunk_kind,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "source_type": chunk.source_type,
                        },
                    )
                    for chunk, vector in zip(batch_chunks, batch_vectors)
                ]
                self.vector_store.upsert(points)

            self.repository.update_document_status(
                doc_id,
                status="completed",
                title=headings[0] if headings else doc["title"],
                summary=summary,
                headings=headings,
                keywords=[],
                chunk_count=len(chunks),
                section_count=max(1, len(headings) or 1),
                page_count=len(extracted.pages),
            )
            duration = time.perf_counter() - started
            self.repository.update_job(job_id, status="completed", stage="completed", progress=1.0, message=f"入库完成，用时 {duration:.2f}s")
            logger.info("ingestion completed doc_id=%s job_id=%s duration=%.2fs chunks=%s", doc_id, job_id, duration, len(chunks))
        except Exception as exc:
            logger.exception("ingestion failed doc_id=%s job_id=%s", doc_id, job_id)
            self.repository.update_document_status(doc_id, status="failed")
            self.repository.update_job(job_id, status="failed", stage="failed", progress=1.0, message="入库失败", error_message=str(exc))
            raise
