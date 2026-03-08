from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentDetail,
    FileItem,
    LibraryCatalogItem,
    ModelProviderItem,
    RetrievalPlan,
    RetrievalTraceItem,
    SectionDetail,
    SourceItem,
    UpdateChunkRequest,
    UpdateDocumentRequest,
    UploadResponse,
)
from app.services.deepseek_client import CompatibleLLMClient
from app.services.document_store import DocumentStore, SUPPORTED_SUFFIXES
from app.services.library_manager import LibraryManager
from app.services.metadata_service import MetadataService
from app.services.rag_engine import RagEngine


settings = get_settings()
document_store = DocumentStore(settings)
llm_client = CompatibleLLMClient(settings)
metadata_service = MetadataService(settings, llm_client)
library_manager = LibraryManager(document_store, metadata_service)
rag_engine = RagEngine(settings, document_store, llm_client)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/library")
async def library_page() -> FileResponse:
    return FileResponse(settings.static_dir / "library.html")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "documents": len(document_store.docs),
        "sections": len(document_store.sections),
        "chunks": len(document_store.chunks),
        "supported_formats": sorted(SUPPORTED_SUFFIXES),
        "providers": llm_client.providers(),
    }


@app.get("/api/models", response_model=list[ModelProviderItem])
async def list_models() -> list[ModelProviderItem]:
    return [ModelProviderItem(**item) for item in llm_client.providers()]


@app.get("/api/files", response_model=list[FileItem])
async def list_files() -> list[FileItem]:
    return [FileItem(**item) for item in document_store.list_files()]


@app.get("/api/library/catalog", response_model=list[LibraryCatalogItem])
async def library_catalog() -> list[LibraryCatalogItem]:
    return [LibraryCatalogItem(**item) for item in document_store.get_catalog()]


@app.get("/api/library/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str) -> DocumentDetail:
    document = document_store.get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetail(**document)


@app.patch("/api/library/{doc_id}", response_model=DocumentDetail)
async def update_document(doc_id: str, payload: UpdateDocumentRequest) -> DocumentDetail:
    document = document_store.update_document_title(doc_id, payload.title)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetail(**document)


@app.patch("/api/library/{doc_id}/chunks/{chunk_id}")
async def update_chunk(doc_id: str, chunk_id: str, payload: UpdateChunkRequest) -> dict:
    chunk = document_store.update_chunk_title(doc_id, chunk_id, payload.chunk_title)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return chunk


@app.delete("/api/library/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    deleted = document_store.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "doc_id": doc_id}


@app.get("/api/library/{doc_id}/sections/{section_id}", response_model=SectionDetail)
async def get_section(doc_id: str, section_id: str) -> SectionDetail:
    section = document_store.get_section(doc_id, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found.")
    return SectionDetail(**section)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    model_provider: str = Form(settings.default_model_provider),
) -> UploadResponse:
    temp_paths: list[Path] = []
    normalized_provider = llm_client.normalize_provider(model_provider)

    for upload in files:
        original_name = Path(upload.filename or "file").name
        suffix = Path(original_name).suffix.lower()
        fd, temp_name = tempfile.mkstemp(suffix=suffix or ".tmp")
        with open(fd, "wb", closefd=True) as tmp:
            tmp.write(await upload.read())
        temp_path = Path(temp_name)
        renamed = temp_path.with_name(f"{temp_path.stem}--{original_name}")
        temp_path.replace(renamed)
        temp_paths.append(renamed)

    result = await library_manager.add_files(temp_paths, model_provider=normalized_provider)
    return UploadResponse(**result)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = await rag_engine.answer_once(payload.message, model_provider=payload.model_provider)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        answer=result["answer"],
        sources=[SourceItem(**source) for source in [rag_engine._source_payload(item) for item in result["sources"]]],
        plan=RetrievalPlan(**result["plan"]),
        emotion=result["emotion"],
        trace=[RetrievalTraceItem(**item) for item in result["trace"]],
    )


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    async def event_stream():
        try:
            async for event in rag_engine.stream_answer(payload.message, model_provider=payload.model_provider):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
