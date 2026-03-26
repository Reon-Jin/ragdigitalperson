from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property

from app.config import Settings
from app.rag.celery_app import celery_app


logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @cached_property
    def pool(self) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=max(1, self.settings.local_task_workers), thread_name_prefix="rag-ingest")

    def submit(self, *, job_id: str, doc_id: str) -> None:
        if self.settings.celery_enabled:
            celery_app.send_task("app.rag.tasks.ingest_document_task", kwargs={"job_id": job_id, "doc_id": doc_id})
            return
        from app.rag.service import build_rag_service

        logger.info("submit local ingestion task doc_id=%s job_id=%s", doc_id, job_id)
        self.pool.submit(build_rag_service().ingestion_service.ingest_document, job_id=job_id, doc_id=doc_id)
