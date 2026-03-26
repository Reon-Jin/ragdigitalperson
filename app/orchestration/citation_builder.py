from __future__ import annotations

from app.knowledge_base.finance_store import FinanceKnowledgeBase
from app.schemas_v2 import CitationItem
from app.services.mysql_document_store import SearchResult


RISK_TERMS = (
    "\u98ce\u9669",
    "\u538b\u529b",
    "\u6ce2\u52a8",
    "\u4e0d\u786e\u5b9a",
)


class CitationBuilder:
    def __init__(self, finance_kb: FinanceKnowledgeBase) -> None:
        self.finance_kb = finance_kb

    def build(self, chunks: list[SearchResult]) -> list[CitationItem]:
        citations: list[CitationItem] = []
        metadata_map = self.finance_kb.get_chunk_metadata_map([item.chunk_id for item in chunks])
        for index, item in enumerate(chunks):
            metadata = metadata_map.get(item.chunk_id, {})
            time_label = metadata.get("report_period") or metadata.get("publish_date")
            section_type = metadata.get("section_type")
            page_start = metadata.get("page_start")
            page_end = metadata.get("page_end")
            chunk_kind = metadata.get("chunk_kind")
            location_parts = [
                f"section={item.section_title or 'unknown'}",
                f"chunk={item.chunk_index + 1}",
            ]
            if page_start and page_end:
                page_label = f"page={page_start}" if page_start == page_end else f"pages={page_start}-{page_end}"
                location_parts.append(page_label)
            if section_type:
                location_parts.append(f"type={section_type}")
            if chunk_kind:
                location_parts.append(f"kind={chunk_kind}")
            citations.append(
                CitationItem(
                    doc_id=item.doc_id,
                    title=item.title,
                    category=item.category,
                    filename=item.filename,
                    section_title=item.section_title,
                    chunk_id=item.chunk_id,
                    chunk_title=item.chunk_title,
                    preview=item.text[:160] + ("..." if len(item.text) > 160 else ""),
                    score=round(item.score, 4),
                    time_label=time_label,
                    location_label=" | ".join(location_parts),
                    page_start=page_start,
                    page_end=page_end,
                    chunk_kind=chunk_kind,
                    section_type=section_type,
                    stance="risk" if index > 0 and any(token in item.text for token in RISK_TERMS) else "support",
                )
            )
        return citations

