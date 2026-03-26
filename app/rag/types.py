from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PageContent:
    page_number: int
    text: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedDocument:
    doc_id: str
    filename: str
    suffix: str
    text: str
    pages: list[PageContent]
    source_type: str = "upload"


@dataclass(slots=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    filename: str
    chunk_index: int
    text: str
    preview: str
    section_title: str
    chunk_kind: str
    source_type: str
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int
    token_count: int
    created_at: str


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    doc_id: str
    filename: str
    title: str
    category: str
    section_title: str
    chunk_index: int
    chunk_title: str
    chunk_kind: str
    page_start: int | None
    page_end: int | None
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
