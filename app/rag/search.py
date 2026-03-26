from __future__ import annotations

from app.config import Settings
from app.rag.embeddings import EmbeddingService
from app.rag.reranker import RerankerService
from app.rag.repositories import RAGRepository
from app.rag.types import SearchHit
from app.rag.vector_store import VectorStore


class SearchService:
    def __init__(self, settings: Settings, repository: RAGRepository, embedding_service: EmbeddingService, reranker: RerankerService, vector_store: VectorStore) -> None:
        self.settings = settings
        self.repository = repository
        self.embedding_service = embedding_service
        self.reranker = reranker
        self.vector_store = vector_store

    def search(self, query: str, *, user_id: str | None = None, doc_id: str | None = None, top_k: int | None = None) -> list[SearchHit]:
        query_vector = self.embedding_service.encode_query(query)
        filter_payload = {}
        if user_id:
            filter_payload["user_id"] = user_id
        if doc_id:
            filter_payload["doc_id"] = doc_id
        raw_hits = self.vector_store.search(query_vector, limit=top_k or self.settings.retrieval_top_k, filter_payload=filter_payload or None)
        chunk_ids = [str(item.id) for item in raw_hits]
        chunk_map = self.repository.get_chunk_map(chunk_ids)
        documents = {item["doc_id"]: item for item in self.repository.list_documents(user_id=user_id)}
        scores = {str(item.id): float(item.score or 0.0) for item in raw_hits}
        rows = [chunk_map[chunk_id] for chunk_id in chunk_ids if chunk_id in chunk_map]
        hits = self.repository.build_search_hits(rows, scores, documents)
        ranked = self.reranker.rerank(query, hits)
        return ranked[: self.settings.answer_top_k]
