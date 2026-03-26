from __future__ import annotations

import logging
import math
import re
from functools import cached_property

import torch
from sentence_transformers import SentenceTransformer

from app.config import Settings


logger = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


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
    def model(self) -> SentenceTransformer | None:
        logger.info("loading embedding model=%s device=%s", self.settings.embedding_model_name, self.device)
        try:
            model = SentenceTransformer(self.settings.embedding_model_name, device=self.device, trust_remote_code=True)
            dimension = model.get_sentence_embedding_dimension()
            if dimension:
                self.settings.embedding_dimensions = dimension
            return model
        except Exception as exc:
            logger.exception("loading embedding model failed, falling back to hashed embeddings: %s", exc)
            return None

    def encode_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.model is None:
            return [self._fallback_encode(text) for text in texts]
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

    def _fallback_encode(self, text: str) -> list[float]:
        dimension = max(128, int(self.settings.embedding_dimensions or 1024))
        vector = [0.0] * dimension
        tokens = TOKEN_PATTERN.findall(text or "")
        if not tokens:
            return vector
        for token in tokens:
            index = hash(token.lower()) % dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
