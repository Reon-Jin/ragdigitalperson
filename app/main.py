from __future__ import annotations

import asyncio
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import require_current_user
from app.api.deps import build_container
from app.api.routes_v2 import router as v2_router
from app.avatar import LocalAvatarService
from app.config import get_settings
from app.knowledge_base.finance_store import FinanceKnowledgeBase
from app.knowledge_base.finance_sync import FinanceSyncService
from app.knowledge_base.profile_store import ProfileStore
from app.rag.service import build_rag_service
from app.schemas import (
    ChatRetrieveRequest,
    ChatRetrieveResponse,
    DocumentDetail,
    FileItem,
    IngestionJobItem,
    LibraryCatalogItem,
    ModelProviderItem,
    PageDetail,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SectionDetail,
    UpdateChunkRequest,
    UpdateDocumentRequest,
    UploadQueuedItem,
    UploadQueuedResponse,
    UploadResponse,
)
from app.services.deepseek_client import CompatibleLLMClient
from app.services.mysql_document_store import DocumentStore, SUPPORTED_SUFFIXES


settings = get_settings()
document_store = DocumentStore(settings)
rug_service = build_rag_service()
llm_client = CompatibleLLMClient(settings)
finance_kb = FinanceKnowledgeBase(settings)
finance_sync = FinanceSyncService(finance_kb, document_store)
profile_store = ProfileStore(settings)
container = build_container(document_store, llm_client, profile_store, finance_kb, finance_sync)
avatar_service = LocalAvatarService(settings)
react_index = settings.static_dir / "app" / "index.html"

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.state.container = container
app.state.avatar_service = avatar_service
app.state.rag_service = rug_service
app.include_router(v2_router)
app.state.finance_sync_status = {"started": False, "done": False, "error": None}


@app.middleware("http")
async def disable_cache_for_finavatar_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/app"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.on_event("startup")
async def startup_background_sync() -> None:
    if not settings.finance_sync_on_startup:
        app.state.finance_sync_status = {"started": False, "done": True, "error": "disabled"}
        return

    app.state.finance_sync_status = {"started": True, "done": False, "error": None}

    async def runner() -> None:
        try:
            if settings.finance_sync_startup_delay_seconds > 0:
                await asyncio.sleep(settings.finance_sync_startup_delay_seconds)
            await asyncio.to_thread(finance_sync.backfill)
            app.state.finance_sync_status = {"started": True, "done": True, "error": None}
        except Exception as exc:
            log_runtime_exception("finance_sync_backfill", exc)
            app.state.finance_sync_status = {"started": True, "done": True, "error": str(exc)}

    asyncio.create_task(runner())


def log_runtime_exception(context: str, exc: Exception) -> None:
    traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    payload = f"[{context}]\n{traceback_text.rstrip()}\n{'-' * 80}\n"
    print(payload, flush=True)
    log_path = settings.data_dir / "runtime-errors.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


@app.get("/")
async def index() -> FileResponse:
    if not react_index.exists():
        raise HTTPException(status_code=503, detail="Frontend bundle not found. Run `npm run build` in web/ first.")
    return FileResponse(react_index)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "database": {
            "backend": document_store.db.backend,
            "dsn_configured": bool(settings.database_url),
            "location": str(
                settings.app_db_path
                if document_store.db.backend == "sqlite"
                else (document_store.db.mysql_config or {}).get("database", "mysql")
            ),
        },
        "rag": {
            "documents": len(document_store.list_files()),
            "sections": len(document_store.sections),
            "chunks": len(document_store.chunks),
            "supported_formats": sorted(SUPPORTED_SUFFIXES),
            "embedding_dimensions": settings.embedding_dimensions,
            "qdrant_collection": settings.qdrant_collection,
            "reranker_enabled": settings.reranker_enabled,
        },
        "finance_kb": finance_kb.stats(),
        "finance_sync": app.state.finance_sync_status,
        "providers": llm_client.providers(),
    }


@app.get("/api/models", response_model=list[ModelProviderItem])
async def list_models() -> list[ModelProviderItem]:
    return [ModelProviderItem(**item) for item in llm_client.providers()]


@app.get("/api/files", response_model=list[FileItem])
async def list_files(request: Request) -> list[FileItem]:
    user = require_current_user(request)
    return [FileItem(**item) for item in document_store.list_files(user_id=user.user_id)]


@app.get("/api/library/catalog", response_model=list[LibraryCatalogItem])
async def library_catalog(request: Request) -> list[LibraryCatalogItem]:
    user = require_current_user(request)
    return [LibraryCatalogItem(**item) for item in document_store.get_catalog(user_id=user.user_id)]


@app.get("/api/library/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str, request: Request) -> DocumentDetail:
    user = require_current_user(request)
    document = document_store.get_document(doc_id, user_id=user.user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetail(**document)


@app.get("/api/library/{doc_id}/pages/{page_number}", response_model=PageDetail)
async def get_document_page(doc_id: str, page_number: int, request: Request) -> PageDetail:
    user = require_current_user(request)
    page = document_store.get_page(doc_id, page_number, user_id=user.user_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    return PageDetail(**page)


@app.patch("/api/library/{doc_id}", response_model=DocumentDetail)
async def update_document(doc_id: str, payload: UpdateDocumentRequest, request: Request) -> DocumentDetail:
    user = require_current_user(request)
    existing = document_store.get_document(doc_id, user_id=user.user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Document not found.")
    document = document_store.update_document_title(doc_id, payload.title)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetail(**document)


@app.patch("/api/library/{doc_id}/chunks/{chunk_id}")
async def update_chunk(doc_id: str, chunk_id: str, payload: UpdateChunkRequest, request: Request) -> dict:
    user = require_current_user(request)
    if not document_store.get_document(doc_id, user_id=user.user_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    chunk = document_store.update_chunk_title(doc_id, chunk_id, payload.chunk_title)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return chunk


@app.delete("/api/library/{doc_id}")
async def delete_document(doc_id: str, request: Request) -> dict:
    user = require_current_user(request)
    deleted = document_store.delete_document(doc_id, user_id=user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "doc_id": doc_id}


@app.get("/api/library/{doc_id}/sections/{section_id}", response_model=SectionDetail)
async def get_section(doc_id: str, section_id: str, request: Request) -> SectionDetail:
    user = require_current_user(request)
    section = document_store.get_section(doc_id, section_id, user_id=user.user_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found.")
    return SectionDetail(**section)


async def _queue_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    model_provider: str = Form(settings.default_model_provider),
) -> UploadQueuedResponse:
    user = require_current_user(request)
    queued_items: list[UploadQueuedItem] = []
    skipped: list[str] = []

    for upload in files:
        original_name = Path(upload.filename or "file").name
        suffix = Path(original_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            skipped.append(original_name)
            continue
        fd, temp_name = tempfile.mkstemp(suffix=suffix or ".tmp")
        with open(fd, "wb", closefd=True) as tmp:
            tmp.write(await upload.read())
        temp_path = Path(temp_name)
        renamed = temp_path.with_name(f"{temp_path.stem}--{original_name}")
        temp_path.replace(renamed)
        try:
            result = rug_service.queue_upload(temp_path=renamed, filename=original_name, user_id=user.user_id)
        except Exception as exc:
            log_runtime_exception("queue_upload", exc)
            renamed.unlink(missing_ok=True)
            skipped.append(original_name)
            continue
        queued_items.append(
            UploadQueuedItem(
                file_id=result["doc"]["doc_id"],
                job_id=result["job"]["job_id"],
                filename=original_name,
                status=result["job"]["status"],
                stage=result["job"]["stage"],
            )
        )
    return UploadQueuedResponse(items=queued_items, skipped=skipped)


@app.post("/api/upload", response_model=UploadQueuedResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    model_provider: str = Form(settings.default_model_provider),
) -> UploadQueuedResponse:
    return await _queue_uploads(request, files=files, model_provider=model_provider)


@app.post("/files/upload", response_model=UploadQueuedResponse)
async def upload_files_v2(
    request: Request,
    files: list[UploadFile] = File(...),
    model_provider: str = Form(settings.default_model_provider),
) -> UploadQueuedResponse:
    return await _queue_uploads(request, files=files, model_provider=model_provider)


@app.get("/jobs/{job_id}", response_model=IngestionJobItem)
async def get_job(job_id: str, request: Request) -> IngestionJobItem:
    user = require_current_user(request)
    job = rug_service.get_job(job_id, user.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return IngestionJobItem(**job)


@app.get("/documents", response_model=list[FileItem])
async def list_documents_v2(request: Request) -> list[FileItem]:
    user = require_current_user(request)
    return [FileItem(**item) for item in rug_service.list_documents(user.user_id)]


@app.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document_v2(doc_id: str, request: Request) -> DocumentDetail:
    user = require_current_user(request)
    document = rug_service.get_document(doc_id, user.user_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DocumentDetail(**document)


@app.delete("/documents/{doc_id}")
async def delete_document_v2(doc_id: str, request: Request) -> dict:
    user = require_current_user(request)
    deleted = rug_service.delete_document(doc_id, user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "doc_id": doc_id}


@app.post("/search", response_model=SearchResponse)
async def semantic_search(payload: SearchRequest, request: Request) -> SearchResponse:
    user = require_current_user(request)
    results = rug_service.search(payload.query, user_id=user.user_id, doc_id=payload.doc_id)
    items = [SearchResultItem(**item) for item in results[: payload.top_k]]
    return SearchResponse(query=payload.query, total=len(items), items=items)


@app.post("/chat/retrieve", response_model=ChatRetrieveResponse)
async def chat_retrieve(payload: ChatRetrieveRequest, request: Request) -> ChatRetrieveResponse:
    user = require_current_user(request)
    results = rug_service.search(payload.query, user_id=user.user_id, doc_id=payload.doc_id)
    items = [SearchResultItem(**item) for item in results[: payload.top_k]]
    return ChatRetrieveResponse(query=payload.query, chunks=items)
