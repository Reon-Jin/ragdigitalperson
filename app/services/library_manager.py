from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Sequence

from app.services.deepseek_client import ModelProvider
from app.services.document_store import DocumentStore, SUPPORTED_SUFFIXES
from app.services.metadata_service import MetadataService


class LibraryManager:
    def __init__(self, document_store: DocumentStore, metadata_service: MetadataService) -> None:
        self.document_store = document_store
        self.metadata_service = metadata_service

    async def add_files(self, file_paths: Sequence[Path], *, model_provider: ModelProvider) -> dict[str, list]:
        prepared_documents = []
        skipped: list[str] = []

        for temp_path in file_paths:
            suffix = temp_path.suffix.lower()
            original_name = self.document_store._extract_original_name(temp_path)
            if suffix not in SUPPORTED_SUFFIXES:
                skipped.append(original_name)
                temp_path.unlink(missing_ok=True)
                continue

            doc_id = str(uuid.uuid4())
            stored_name = f"{doc_id}{suffix}"
            destination = self.document_store.settings.uploads_dir / stored_name
            shutil.move(str(temp_path), destination)

            try:
                prepared = self.document_store.prepare_document(destination, original_name, preserve_doc_id=doc_id)
            except Exception:
                destination.unlink(missing_ok=True)
                skipped.append(original_name)
                continue

            if prepared is None:
                destination.unlink(missing_ok=True)
                skipped.append(original_name)
                continue

            enriched = await self.metadata_service.enrich_document(
                filename=original_name,
                text_excerpt=prepared["text_excerpt"],
                headings=prepared["doc"].get("headings", []),
                chunks=prepared["chunks"],
                model_provider=model_provider,
            )
            prepared_documents.append(self.document_store.apply_metadata(prepared, enriched))

        added = self.document_store.save_prepared_documents(prepared_documents)
        return {"added": added, "skipped": skipped}
