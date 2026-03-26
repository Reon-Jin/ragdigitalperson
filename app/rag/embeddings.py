from __future__ import annotations

import logging
from functools import cached_property

import torch
from sentence_transformers import SentenceTransformer

from app.config import Settings


logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def device(self) -> str:
        requested = self.settings.embedding_device
        if requested != "auto":
            return requested
        return "cuda" if torch.cuda.is_available() else "cpu"

    @cached_property
    def model(self) -> SentenceTransformer:
        logger.info("loading embedding model=%s device=%s", self.settings.embedding_model_name, self.device)
        model = SentenceTransformer(self.settings.embedding_model_name, device=self.device, trust_remote_code=True)
        dimension = model.get_sentence_embedding_dimension()
        if dimension:
            self.settings.embedding_dimensions = dimension
        return model

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.settings.embedding_batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [vector.astype(float).tolist() for vector in vectors]

    def encode_query(self, query: str) -> list[float]:
        return self.encode_texts([query])[0]
