from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseModel):
    app_name: str = "RAG Digital Person"
    deepseek_api_key: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    qwen_api_key: str = Field(default_factory=lambda: os.getenv("QWEN_API_KEY", ""))
    qwen_base_url: str = Field(
        default_factory=lambda: os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    )
    qwen_model: str = Field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-plus"))
    default_model_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_MODEL_PROVIDER", "deepseek"))
    uploads_dir: Path = BASE_DIR / "uploads"
    data_dir: Path = BASE_DIR / "data"
    static_dir: Path = BASE_DIR / "static"
    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 4
    max_doc_candidates: int = 4
    max_section_candidates: int = 8
    max_chunk_candidates: int = 10
    min_retrieval_score: float = 0.09
    allowed_categories: tuple[str, ...] = ("金融", "医学", "法律", "科技", "生活")
    metadata_excerpt_chars: int = 3500
    chunk_title_batch_size: int = 10
    multi_select_doc_limit: int = 5
    multi_select_chunk_limit: int = 8


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.static_dir.mkdir(parents=True, exist_ok=True)
    return settings
