from __future__ import annotations

from app.knowledge_base.finance_store import FinanceKnowledgeBase
from app.services.mysql_document_store import DocumentStore


class FinanceSyncService:
    def __init__(self, finance_kb: FinanceKnowledgeBase, document_store: DocumentStore) -> None:
        self.finance_kb = finance_kb
        self.document_store = document_store

    def backfill(self) -> dict:
        synced = 0
        for item in self.document_store.list_files():
            if item.get("user_id"):
                continue
            detail = self.document_store.get_document(item["doc_id"])
            if not detail:
                continue
            self.finance_kb.upsert_document(detail)
            synced += 1
        return {"synced_documents": synced, **self.finance_kb.stats()}

    def sync_document(self, doc_id: str) -> None:
        detail = self.document_store.get_document(doc_id)
        if not detail or detail.get("user_id"):
            return
        self.finance_kb.upsert_document(detail)
