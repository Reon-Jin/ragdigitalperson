from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from transformers import AutoTokenizer

from app.config import Settings
from app.rag.types import ChunkRecord, ExtractedDocument


@dataclass(slots=True)
class TextBlock:
    text: str
    kind: str
    section_title: str
    page_number: int | None


class Chunker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tokenizer = AutoTokenizer.from_pretrained(settings.tokenizer_name, trust_remote_code=True)

    def chunk(self, document: ExtractedDocument) -> list[ChunkRecord]:
        blocks = self._collect_blocks(document)
        chunks: list[ChunkRecord] = []
        cursor = 0
        created_at = datetime.now(timezone.utc).isoformat()
        for block in blocks:
            if not block.text.strip():
                continue
            for piece in self._split_block(block.text):
                token_count = self._count_tokens(piece)
                preview = re.sub(r"\s+", " ", piece).strip()[:240]
                chunks.append(
                    ChunkRecord(
                        chunk_id=str(uuid.uuid4()),
                        doc_id=document.doc_id,
                        filename=document.filename,
                        chunk_index=len(chunks),
                        text=piece,
                        preview=preview,
                        section_title=block.section_title,
                        chunk_kind=block.kind,
                        source_type=document.source_type,
                        page_start=block.page_number,
                        page_end=block.page_number,
                        char_start=cursor,
                        char_end=cursor + len(piece),
                        token_count=token_count,
                        created_at=created_at,
                    )
                )
                cursor += len(piece) + 2
        return chunks

    def _collect_blocks(self, document: ExtractedDocument) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        current_section = self._default_title(document.filename)
        for page in document.pages:
            if page.blocks:
                for block in page.blocks:
                    text = str(block.get("text", "")).strip()
                    if not text:
                        continue
                    kind = str(block.get("kind", "text"))
                    if kind == "heading":
                        current_section = text.lstrip("# ").strip() or current_section
                        continue
                    blocks.append(TextBlock(text=text, kind=kind, section_title=current_section, page_number=page.page_number))
                continue
            for paragraph in self._split_paragraphs(page.text):
                kind = self._detect_kind(paragraph)
                if kind == "heading":
                    current_section = paragraph.lstrip("# ").strip() or current_section
                    continue
                blocks.append(TextBlock(text=paragraph, kind=kind, section_title=current_section, page_number=page.page_number))
        return blocks

    def _split_block(self, text: str) -> list[str]:
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        if len(token_ids) <= self.settings.chunk_size_tokens:
            return [text]
        chunks: list[str] = []
        start = 0
        size = self.settings.chunk_size_tokens
        overlap = self.settings.chunk_overlap_tokens
        while start < len(token_ids):
            end = min(len(token_ids), start + size)
            segment = self.tokenizer.decode(token_ids[start:end], skip_special_tokens=True).strip()
            if segment:
                chunks.append(segment)
            if end >= len(token_ids):
                break
            start = max(0, end - overlap)
        return chunks

    def _split_paragraphs(self, text: str) -> list[str]:
        return [item.strip() for item in re.split(r"\n{2,}", text.replace("\r", "\n")) if item.strip()]

    def _detect_kind(self, text: str) -> str:
        probe = text.strip()
        if probe.startswith("```"):
            return "code"
        if "|" in probe or "\t" in probe:
            return "table"
        if re.match(r"^#{1,6}\s+", probe) or re.match(r"^(\d+(\.\d+){0,3}|第[一二三四五六七八九十百千]+[章节部分])", probe):
            return "heading"
        if re.search(r"[=+\-*/]{2,}", probe):
            return "formula"
        return "text"

    def _count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def _default_title(self, filename: str) -> str:
        return re.sub(r"\.[^.]+$", "", filename).strip() or "文档"
