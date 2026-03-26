from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _default_database_url() -> str:
    explicit_url = (
        os.getenv("MYSQL_DSN")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    if explicit_url:
        return explicit_url
    mysql_password = os.getenv("MYSQL_PASSWORD", "").strip()
    mysql_enabled = any(
        os.getenv(key, "").strip()
        for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_DATABASE", "MYSQL_PASSWORD")
    )
    if not mysql_enabled:
        return ""
    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
    mysql_port = os.getenv("MYSQL_PORT", "3306").strip() or "3306"
    mysql_user = os.getenv("MYSQL_USER", "root").strip() or "root"
    mysql_database = os.getenv("MYSQL_DATABASE", "finavatar").strip() or "finavatar"
    return (
        f"mysql://{quote_plus(mysql_user)}:{quote_plus(mysql_password)}"
        f"@{mysql_host}:{mysql_port}/{quote_plus(mysql_database)}?charset=utf8mb4"
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "FinAvatar"
    deepseek_api_key: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    qwen_api_key: str = Field(default_factory=lambda: os.getenv("QWEN_API_KEY", ""))
    qwen_base_url: str = Field(default_factory=lambda: os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    qwen_model: str = Field(default_factory=lambda: os.getenv("QWEN_MODEL", "qwen-plus"))
    mimo_api_key: str = Field(default_factory=lambda: os.getenv("MIMO_API_KEY", ""))
    mimo_base_url: str = Field(default_factory=lambda: os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"))
    mimo_model: str = Field(default_factory=lambda: os.getenv("MIMO_MODEL", "mimo-v2-flash"))
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:4b"))
    default_model_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_MODEL_PROVIDER", "deepseek"))

    uploads_dir: Path = BASE_DIR / "uploads"
    data_dir: Path = BASE_DIR / "data"
    finance_db_path: Path = BASE_DIR / "data" / "finance_kb.sqlite3"
    app_db_path: Path = BASE_DIR / "data" / "finavatar_app.sqlite3"
    static_dir: Path = BASE_DIR / "static"
    database_url: str = Field(default_factory=_default_database_url)
    embedding_dimensions: int = Field(default_factory=lambda: int(os.getenv("EMBEDDING_DIMENSIONS", "512")))

    chunk_size: int = 900
    chunk_overlap: int = 120
    top_k: int = 4
    max_doc_candidates: int = 4
    max_section_candidates: int = 8
    max_chunk_candidates: int = 10
    min_retrieval_score: float = 0.09
    allowed_categories: tuple[str, ...] = ("金融", "科技", "法律", "医学", "生活")
    metadata_excerpt_chars: int = 3500
    chunk_title_batch_size: int = 10
    multi_select_doc_limit: int = 5
    multi_select_chunk_limit: int = 8
    finance_response_modes: tuple[str, ...] = ("summary", "advisor", "teaching")
    finance_personas: tuple[str, ...] = ("advisor", "researcher", "teacher")
    finance_task_types: tuple[str, ...] = (
        "general_finance_qa",
        "stock_analysis",
        "earnings_report_analysis",
        "news_explainer",
        "sector_analysis",
        "portfolio_assistant",
        "teaching_mode",
    )
    finance_sync_on_startup: bool = Field(default_factory=lambda: _env_bool("FINANCE_SYNC_ON_STARTUP", False))
    finance_sync_startup_delay_seconds: float = Field(default_factory=lambda: float(os.getenv("FINANCE_SYNC_STARTUP_DELAY_SECONDS", "0")))
    market_default_region: str = Field(default_factory=lambda: os.getenv("MARKET_DEFAULT_REGION", "CN"))
    market_quote_cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_QUOTE_CACHE_TTL_SECONDS", "15")))
    market_board_cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_BOARD_CACHE_TTL_SECONDS", "60")))
    market_fundamentals_cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_FUNDAMENTALS_CACHE_TTL_SECONDS", "3600")))
    market_news_cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_NEWS_CACHE_TTL_SECONDS", "45")))
    market_result_cache_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_RESULT_CACHE_TTL_SECONDS", "90")))
    market_provider_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MARKET_PROVIDER_TIMEOUT_SECONDS", "8")))
    market_provider_max_retries: int = Field(default_factory=lambda: int(os.getenv("MARKET_PROVIDER_MAX_RETRIES", "2")))
    market_provider_qps: int = Field(default_factory=lambda: int(os.getenv("MARKET_PROVIDER_QPS", "5")))
    market_provider_concurrency: int = Field(default_factory=lambda: int(os.getenv("MARKET_PROVIDER_CONCURRENCY", "4")))
    market_health_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MARKET_HEALTH_TIMEOUT_SECONDS", "0.25")))
    market_analysis_quote_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MARKET_ANALYSIS_QUOTE_TIMEOUT_SECONDS", "1.2")))
    market_analysis_component_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MARKET_ANALYSIS_COMPONENT_TIMEOUT_SECONDS", "1.0")))
    market_analysis_history_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("MARKET_ANALYSIS_HISTORY_TIMEOUT_SECONDS", "1.4")))
    market_primary_quote_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_QUOTE_PROVIDER", "chinafast"))
    market_primary_fund_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_FUND_PROVIDER", "mock"))
    market_primary_news_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_NEWS_PROVIDER", "akshare"))
    market_primary_fundamentals_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_FUNDAMENTALS_PROVIDER", "akshare"))
    market_primary_screener_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_SCREENER_PROVIDER", "akshare"))
    market_primary_technical_provider: str = Field(default_factory=lambda: os.getenv("MARKET_PRIMARY_TECHNICAL_PROVIDER", "akshare"))
    market_fallback_order: tuple[str, ...] = Field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.getenv("MARKET_FALLBACK_ORDER", "chinafast,mock").split(",")
            if item.strip()
        )
    )
    market_circuit_breaker_failures: int = Field(default_factory=lambda: int(os.getenv("MARKET_CIRCUIT_BREAKER_FAILURES", "3")))
    market_circuit_breaker_reset_seconds: int = Field(default_factory=lambda: int(os.getenv("MARKET_CIRCUIT_BREAKER_RESET_SECONDS", "30")))
    market_style: str = Field(default_factory=lambda: os.getenv("MARKET_STYLE", "cn_market"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.static_dir.mkdir(parents=True, exist_ok=True)
    return settings
