from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


CategoryName = str
EmotionName = Literal["neutral", "happy", "serious", "concerned", "energetic", "thinking"]
ModelProviderName = Literal["deepseek", "qwen", "mimo", "ollama"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model_provider: ModelProviderName = "deepseek"


class RetrievalPlan(BaseModel):
    should_retrieve: bool
    mode: Literal["none", "shallow", "deep"]
    reason: str
    queries: List[str]
    target_granularity: Literal["document", "section", "chunk"]
    selected_categories: List[CategoryName] = Field(default_factory=list)
    selected_documents: List[str] = Field(default_factory=list)
    selected_chunk_ids: List[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    doc_id: str
    filename: str
    category: CategoryName
    title: str
    section_id: str
    section_title: str
    chunk_id: str
    chunk_index: int
    chunk_title: str
    score: float
    preview: str


class RetrievalTraceItem(BaseModel):
    id: str
    label: str
    score: float
    level: Literal["category", "document", "section", "chunk"]
    parent_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    plan: RetrievalPlan
    emotion: EmotionName
    trace: List[RetrievalTraceItem]


class FileItem(BaseModel):
    doc_id: str
    filename: str
    category: CategoryName
    title: str
    suffix: str
    uploaded_at: str
    chunk_count: int
    section_count: int
    summary: str
    keywords: List[str] = Field(default_factory=list)
    status: str = "queued"
    is_active: bool = True


class UploadResponse(BaseModel):
    added: List[FileItem]
    skipped: List[str]


class IngestionJobItem(BaseModel):
    job_id: str
    doc_id: str
    user_id: str
    filename: str
    status: str
    stage: str
    progress: float
    message: str = ""
    error_message: str | None = None
    retry_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class UploadQueuedItem(BaseModel):
    file_id: str
    job_id: str
    filename: str
    status: str
    stage: str


class UploadQueuedResponse(BaseModel):
    items: List[UploadQueuedItem]
    skipped: List[str] = Field(default_factory=list)


class ChunkPreview(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_title: str
    chunk_kind: str = "text"
    section_id: str
    section_title: str
    preview: str
    word_count: int
    page_start: int | None = None
    page_end: int | None = None


class SectionSummary(BaseModel):
    section_id: str
    doc_id: str
    title: str
    order: int
    summary: str
    chunk_count: int = 0
    previews: List[ChunkPreview]


class DocumentDetail(BaseModel):
    doc_id: str
    filename: str
    category: CategoryName
    title: str
    suffix: str
    uploaded_at: str
    chunk_count: int
    section_count: int
    summary: str
    keywords: List[str] = Field(default_factory=list)
    status: str = "queued"
    is_active: bool = True
    headings: List[str]
    sections: List[SectionSummary]
    chunks: List["ChunkDetail"]
    pages: List["PageDetail"] = Field(default_factory=list)


class ChunkDetail(BaseModel):
    chunk_id: str
    chunk_index: int
    chunk_title: str
    section_id: str
    section_title: str
    text: str
    preview: str
    chunk_kind: str = "text"
    word_count: int
    char_start: int
    char_end: int
    page_start: int | None = None
    page_end: int | None = None


class PageDetail(BaseModel):
    doc_id: str
    page_number: int
    char_start: int
    char_end: int
    preview: str
    text: str = ""
    chunks: List[ChunkPreview] = Field(default_factory=list)


class SectionDetail(BaseModel):
    section_id: str
    doc_id: str
    title: str
    order: int
    summary: str
    chunks: List[ChunkDetail]


class LibraryCatalogChunk(BaseModel):
    chunk_id: str
    chunk_title: str
    chunk_kind: str = "text"
    section_id: str
    section_title: str
    chunk_index: int
    preview: str
    page_start: int | None = None
    page_end: int | None = None


class LibraryCatalogItem(BaseModel):
    doc_id: str
    filename: str
    category: CategoryName
    title: str
    summary: str
    keywords: List[str] = Field(default_factory=list)
    is_active: bool = True
    chunks: List[LibraryCatalogChunk]


class UpdateDocumentRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class UpdateChunkRequest(BaseModel):
    chunk_title: str = Field(min_length=1, max_length=80)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=30, ge=1, le=100)
    doc_id: str | None = None


class SearchResultItem(BaseModel):
    doc_id: str
    filename: str
    category: str
    title: str
    section_id: str
    section_title: str
    chunk_id: str
    chunk_index: int
    chunk_title: str
    score: float
    text: str
    page_start: int | None = None
    page_end: int | None = None
    chunk_kind: str = "text"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    total: int
    items: List[SearchResultItem]


class ChatRetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=6, ge=1, le=20)
    doc_id: str | None = None


class ChatRetrieveResponse(BaseModel):
    query: str
    chunks: List[SearchResultItem]


class ModelProviderItem(BaseModel):
    id: ModelProviderName
    label: str
    model: str
    configured: bool
