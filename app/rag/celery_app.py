from __future__ import annotations

from celery import Celery

from app.config import get_settings


settings = get_settings()
celery_app = Celery("rag_ingestion", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_always_eager=settings.celery_always_eager)
