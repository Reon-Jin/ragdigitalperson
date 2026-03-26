from __future__ import annotations

from functools import cached_property
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest

from app.config import Settings


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def client(self) -> QdrantClient:
        if self.settings.qdrant_url:
            return QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key or None, timeout=30)
        return QdrantClient(path=str(self.settings.qdrant_path))

    def ensure_collection(self) -> None:
        collections = {item.name for item in self.client.get_collections().collections}
        if self.settings.qdrant_collection in collections:
            return
        self.client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config=rest.VectorParams(size=self.settings.embedding_dimensions, distance=rest.Distance.COSINE),
        )

    def upsert(self, points: list[rest.PointStruct]) -> None:
        if not points:
            return
        self.ensure_collection()
        self.client.upsert(collection_name=self.settings.qdrant_collection, points=points, wait=True)

    def search(self, query_vector: list[float], *, limit: int, filter_payload: dict[str, Any] | None = None) -> list[Any]:
        self.ensure_collection()
        query_filter = None
        if filter_payload:
            query_filter = rest.Filter(
                must=[rest.FieldCondition(key=key, match=rest.MatchValue(value=value)) for key, value in filter_payload.items()]
            )
        return self.client.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.ensure_collection()
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=rest.FilterSelector(
                filter=rest.Filter(must=[rest.FieldCondition(key="doc_id", match=rest.MatchValue(value=doc_id))])
            ),
            wait=True,
        )
