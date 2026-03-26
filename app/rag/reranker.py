from __future__ import annotations

import logging
from functools import cached_property

import torch
from FlagEmbedding import FlagReranker

from app.config import Settings
from app.rag.types import SearchHit


logger = logging.getLogger(__name__)


class RerankerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def enabled(self) -> bool:
        return self.settings.reranker_enabled

    @cached_property
    def device(self) -> str:
        requested = self.settings.reranker_device
        if requested != "auto":
            return requested
        return "cuda" if torch.cuda.is_available() else "cpu"

    @cached_property
    def model(self) -> FlagReranker | None:
        logger.info("loading reranker model=%s device=%s", self.settings.reranker_model_name, self.device)
        try:
            return FlagReranker(self.settings.reranker_model_name, use_fp16=self.device.startswith("cuda"), device=self.device)
        except Exception as exc:
            logger.exception("loading reranker failed, disabling rerank: %s", exc)
            return None

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        if not self.enabled or not hits or self.model is None:
            return hits
        pairs = [[query, hit.text] for hit in hits]
        scores = self.model.compute_score(pairs, batch_size=self.settings.reranker_batch_size)
        for hit, score in zip(hits, scores):
            hit.score = float(score)
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: self.settings.rerank_top_n]
