from __future__ import annotations

from app.rag.celery_app import celery_app
from app.rag.service import build_rag_service


@celery_app.task(name="app.rag.tasks.ingest_document_task")
def ingest_document_task(job_id: str, doc_id: str) -> None:
    build_rag_service().ingestion_service.ingest_document(job_id=job_id, doc_id=doc_id)
