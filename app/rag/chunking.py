from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.rag.types import ChunkRecord, ExtractedDocument


logger = logging.getLogger(__name__)

try:
    from transformers import AutoTokenizer  # type: ignore
except Exception:  # pragma: no cover
    AutoTokenizer = None


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]")


@dataclass(slots=True)
class TextBlock:
    text: str
    kind: str
    section_title: str
    page_number: int | None


class Chunker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._tokenizer: Any | None = None
        self._tokenizer_failed = False

    def chunk(self, document: ExtractedDocument) -> list[ChunkRecord]:
        blocks = self._merge_blocks(self._collect_blocks(document))
        chunks: list[ChunkRecord] = []
        cursor = 0
        created_at = datetime.now(timezone.utc).isoformat()
        seen_signatures: set[str] = set()
        for block in blocks:
            if not block.text.strip():
                continue
            for piece in self._split_block(block.text):
                cleaned = piece.strip()
                if not cleaned:
                    continue
                signature = self._signature(cleaned)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                token_count = self._count_tokens(cleaned)
                preview = re.sub(r"\s+", " ", cleaned).strip()[:240]
                chunks.append(
                    ChunkRecord(
                        chunk_id=str(uuid.uuid4()),
                        doc_id=document.doc_id,
                        filename=document.filename,
                        chunk_index=len(chunks),
                        text=cleaned,
                        preview=preview,
                        section_title=block.section_title,
                        chunk_kind=block.kind,
                        source_type=document.source_type,
                        page_start=block.page_number,
                        page_end=block.page_number,
                        char_start=cursor,
                        char_end=cursor + len(cleaned),
                        token_count=token_count,
                        created_at=created_at,
                    )
                )
                cursor += len(cleaned) + 2
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
        tokenizer = self._get_tokenizer()
        if tokenizer is not None:
            try:
                token_ids = tokenizer.encode(text, add_special_tokens=False)
                if len(token_ids) <= self.settings.chunk_size_tokens:
                    return [text]
                chunks: list[str] = []
                start = 0
                size = self.settings.chunk_size_tokens
                overlap = self.settings.chunk_overlap_tokens
                while start < len(token_ids):
                    end = min(len(token_ids), start + size)
                    segment = tokenizer.decode(token_ids[start:end], skip_special_tokens=True).strip()
                    if segment:
                        chunks.append(segment)
                    if end >= len(token_ids):
                        break
                    start = max(0, end - overlap)
                if chunks:
                    return chunks
            except Exception as exc:
                logger.warning("hf tokenizer chunking failed, fallback to regex tokenizer: %s", exc)
                self._tokenizer_failed = True

        spans = [(match.start(), match.end()) for match in TOKEN_PATTERN.finditer(text)]
        if len(spans) <= self.settings.chunk_size_tokens:
            return [text]
        chunks: list[str] = []
        start = 0
        size = self.settings.chunk_size_tokens
        overlap = self.settings.chunk_overlap_tokens
        while start < len(spans):
            end = min(len(spans), start + size)
            char_start = spans[start][0]
            char_end = spans[end - 1][1]
            segment = text[char_start:char_end].strip()
            if segment:
                chunks.append(segment)
            if end >= len(spans):
                break
            start = max(0, end - overlap)
        return chunks or [text]

    def _merge_blocks(self, blocks: list[TextBlock]) -> list[TextBlock]:
        merged: list[TextBlock] = []
        seen_short_blocks: set[str] = set()
        for block in blocks:
            normalized = re.sub(r"\s+", " ", block.text).strip()
            if len(normalized) < 20:
                continue
            short_signature = self._signature(normalized)
            if len(normalized) < 80 and short_signature in seen_short_blocks:
                continue
            if len(normalized) < 80:
                seen_short_blocks.add(short_signature)
            if merged:
                last = merged[-1]
                last_tokens = self._count_tokens(last.text)
                current_tokens = self._count_tokens(normalized)
                if (
                    block.kind == last.kind == "text"
                    and block.section_title == last.section_title
                    and block.page_number == last.page_number
                    and last_tokens < max(80, self.settings.chunk_overlap_tokens)
                    and (last_tokens + current_tokens) <= self.settings.chunk_size_tokens
                ):
                    merged[-1] = TextBlock(
                        text=f"{last.text}\n\n{normalized}",
                        kind=last.kind,
                        section_title=last.section_title,
                        page_number=last.page_number,
                    )
                    continue
            merged.append(TextBlock(text=normalized, kind=block.kind, section_title=block.section_title, page_number=block.page_number))
        return merged

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
        tokenizer = self._get_tokenizer()
        if tokenizer is not None and not self._tokenizer_failed:
            try:
                return len(tokenizer.encode(text, add_special_tokens=False))
            except Exception as exc:
                logger.warning("hf tokenizer token count failed, fallback to regex tokenizer: %s", exc)
                self._tokenizer_failed = True
        return len(TOKEN_PATTERN.findall(text))

    def _signature(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        if len(normalized) > 160:
            normalized = normalized[:160]
        return normalized

    def _get_tokenizer(self) -> Any | None:
        if self._tokenizer_failed or AutoTokenizer is None:
            return None
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.settings.tokenizer_name,
                trust_remote_code=True,
                local_files_only=True,
            )
            return self._tokenizer
        except Exception as exc:
            logger.warning("load tokenizer failed, fallback to regex tokenizer: model=%s error=%s", self.settings.tokenizer_name, exc)
            self._tokenizer_failed = True
            return None

    def _default_title(self, filename: str) -> str:
        return re.sub(r"\.[^.]+$", "", filename).strip() or "文档"
