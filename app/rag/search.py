import math
import re
from collections import Counter

from app.config import Settings
from app.rag.embeddings import EmbeddingService
from app.rag.reranker import RerankerService
from app.rag.repositories import RAGRepository
from app.rag.types import SearchHit
from app.rag.vector_store import VectorStore


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{1,2}|[A-Za-z0-9_]+")


class SearchService:
    def __init__(self, settings: Settings, repository: RAGRepository, embedding_service: EmbeddingService, reranker: RerankerService, vector_store: VectorStore) -> None:
        self.settings = settings
        self.repository = repository
        self.embedding_service = embedding_service
        self.reranker = reranker
        self.vector_store = vector_store

    def search(self, query: str, *, user_id: str | None = None, doc_id: str | None = None, top_k: int | None = None) -> list[SearchHit]:
        limit = top_k or self.settings.retrieval_top_k
        documents = {item["doc_id"]: item for item in self.repository.list_documents(user_id=user_id, active_only=True)}
        try:
            vector_hits = self._vector_search(query, documents=documents, user_id=user_id, doc_id=doc_id, limit=limit)
        except Exception:
            vector_hits = []
        lexical_hits = self._lexical_search(query, documents=documents, user_id=user_id, doc_id=doc_id, limit=limit)
        merged = self._merge_hits(vector_hits, lexical_hits)
        try:
            ranked = self.reranker.rerank(query, merged)
        except Exception:
            ranked = merged
        return ranked[: self.settings.answer_top_k]

    def _vector_search(self, query: str, *, documents: dict[str, dict], user_id: str | None, doc_id: str | None, limit: int) -> list[SearchHit]:
        if doc_id and doc_id not in documents:
            return []
        query_vector = self.embedding_service.encode_query(query)
        filter_payload = {}
        if user_id:
            filter_payload["user_id"] = user_id
        if doc_id:
            filter_payload["doc_id"] = doc_id
        raw_hits = self.vector_store.search(query_vector, limit=limit, filter_payload=filter_payload or None)
        chunk_ids = [str(item.id) for item in raw_hits]
        chunk_map = self.repository.get_chunk_map(chunk_ids)
        scores = {str(item.id): float(item.score or 0.0) for item in raw_hits}
        rows = [chunk_map[chunk_id] for chunk_id in chunk_ids if chunk_id in chunk_map and chunk_map[chunk_id]["doc_id"] in documents]
        return self.repository.build_search_hits(rows, scores, documents)

    def _lexical_search(self, query: str, *, documents: dict[str, dict], user_id: str | None, doc_id: str | None, limit: int) -> list[SearchHit]:
        if doc_id and doc_id not in documents:
            return []
        rows = self.repository.list_chunks(doc_id=doc_id, user_id=user_id)
        query_counter = Counter(self._tokenize(query))
        if not query_counter:
            return []
        normalized_query = re.sub(r"\s+", "", query.lower())
        scores: dict[str, float] = {}
        selected_rows: list[dict] = []
        for row in rows:
            doc = documents.get(row["doc_id"])
            if not doc:
                continue
            title = str(doc.get("title", ""))
            text = "\n".join([title, title, str(row.get("section_title", "")), str(row.get("text", ""))])
            score = self._lexical_score(query_counter, Counter(self._tokenize(text)))
            score += self._title_boost(query_counter, normalized_query, title)
            if score <= 0:
                continue
            scores[row["chunk_id"]] = score
            selected_rows.append(row)
        selected_rows.sort(key=lambda item: scores.get(item["chunk_id"], 0.0), reverse=True)
        return self.repository.build_search_hits(selected_rows[:limit], scores, documents)

    def _merge_hits(self, vector_hits: list[SearchHit], lexical_hits: list[SearchHit]) -> list[SearchHit]:
        merged: dict[str, SearchHit] = {}
        for hit in lexical_hits:
            hit.score = hit.score * 0.35
            merged[hit.chunk_id] = hit
        for hit in vector_hits:
            existing = merged.get(hit.chunk_id)
            if existing:
                existing.score = max(existing.score, hit.score * 0.65 + existing.score)
            else:
                hit.score = hit.score * 0.65
                merged[hit.chunk_id] = hit
        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return ranked

    def _tokenize(self, text: str) -> list[str]:
        return [item.lower() for item in TOKEN_PATTERN.findall(text or "") if item.strip()]

    def _title_boost(self, query_counter: Counter[str], normalized_query: str, title: str) -> float:
        normalized_title = re.sub(r"\s+", "", (title or "").lower())
        if not normalized_title:
            return 0.0
        score = self._lexical_score(query_counter, Counter(self._tokenize(title))) * 1.2
        if normalized_query and normalized_title:
            if normalized_title in normalized_query:
                score += 1.5
            elif normalized_query in normalized_title:
                score += 0.9
        return score

    def _lexical_score(self, query_counter: Counter[str], doc_counter: Counter[str]) -> float:
        overlap = 0.0
        query_norm = 0.0
        doc_norm = 0.0
        for token, count in query_counter.items():
            weight = 1.0 + math.log(1 + count)
            query_norm += weight * weight
            if token in doc_counter:
                overlap += weight * (1.0 + math.log(1 + doc_counter[token]))
        for token, count in doc_counter.items():
            weight = 1.0 + math.log(1 + count)
            doc_norm += weight * weight
        if overlap <= 0:
            return 0.0
        return overlap / max(math.sqrt(query_norm * doc_norm), 1e-6)