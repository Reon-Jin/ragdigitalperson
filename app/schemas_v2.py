from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


V2TaskType = Literal[
    "auto",
    "realtime_quote",
    "stock_analysis",
    "stock_recommendation_analysis",
    "fund_analysis",
    "fund_screening",
    "sector_rotation_analysis",
    "finance_knowledge_qa",
]
ResolvedV2TaskType = Literal[
    "realtime_quote",
    "stock_analysis",
    "stock_recommendation_analysis",
    "fund_analysis",
    "fund_screening",
    "sector_rotation_analysis",
    "finance_knowledge_qa",
]
AnalysisMode = Literal["summary", "professional", "teaching"]
ModelProviderType = Literal["deepseek", "qwen", "mimo", "ollama"]
ChatRole = Literal["user", "assistant"]


class ChatHistoryTurn(BaseModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=12000)


class ConversationContextHint(BaseModel):
    task_type: ResolvedV2TaskType | None = None
    symbol: str | None = None
    fund_code: str | None = None
    company: str | None = None
    sector: str | None = None


class HybridCopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    task_type: V2TaskType = "auto"
    analysis_mode: AnalysisMode = "professional"
    profile_id: str = "default"
    user_id: str | None = None
    model_provider: ModelProviderType = "deepseek"
    conversation_id: str | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list)
    context_hint: ConversationContextHint | None = None


class UserProfile(BaseModel):
    profile_id: str = "default"
    risk_level: Literal["low", "medium", "high"] = "medium"
    investment_horizon: Literal["short", "medium", "long"] = "medium"
    markets: list[str] = Field(default_factory=lambda: ["A-share"])
    sector_preferences: list[str] = Field(default_factory=list)
    style_preference: Literal["summary", "advisor", "teaching"] = "advisor"


class CitationItem(BaseModel):
    doc_id: str
    title: str
    category: str
    filename: str
    section_title: str
    chunk_id: str
    chunk_title: str
    preview: str
    score: float
    time_label: str | None = None
    location_label: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    chunk_kind: Literal["text", "table"] | None = None
    section_type: str | None = None
    stance: Literal["support", "risk", "counter"] = "support"


class V2RouteDecision(BaseModel):
    task_type: ResolvedV2TaskType
    reason: str
    symbol: str | None = None
    fund_code: str | None = None
    company: str | None = None
    sector: str | None = None
    needs_market_data: bool = True
    needs_rag: bool = False


class ConversationMessage(BaseModel):
    message_id: str
    role: ChatRole
    content: str
    created_at: str
    task_type: str | None = None
    route: dict[str, Any] | None = None


class ConversationSession(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message_preview: str | None = None


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class HybridAnswerPayload(BaseModel):
    route: V2RouteDecision
    answer: str
    cards: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthUser(BaseModel):
    user_id: str
    username: str
    display_name: str
    created_at: str
    last_login_at: str


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    username: str = Field(default="", max_length=40)
    password: str = Field(default="", max_length=120)
    display_name: str | None = Field(
        default=None,
        max_length=40,
        validation_alias=AliasChoices("display_name", "displayName"),
    )

    @field_validator("username", "display_name", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    username: str = Field(default="", max_length=40)
    password: str = Field(default="", max_length=120)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_string(cls, value: str | None) -> str:
        return str(value or "").strip()


class AuthResponse(BaseModel):
    token: str
    user: AuthUser


class SessionResponse(BaseModel):
    authenticated: bool
    user: AuthUser | None = None


class AgentEventRequest(BaseModel):
    event_type: str = Field(min_length=2, max_length=60)
    summary: str = Field(default="", max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMemorySnapshot(BaseModel):
    user_id: str
    summary: str
    recent_symbols: list[str] = Field(default_factory=list)
    recent_sectors: list[str] = Field(default_factory=list)
    preference_tags: list[str] = Field(default_factory=list)
    recent_tasks: list[str] = Field(default_factory=list)
    recent_actions: list[str] = Field(default_factory=list)
    updated_at: str


class LocalAvatarProfile(BaseModel):
    avatar_id: str = "local-avatar"
    display_name: str = Field(default="FinAvatar Analyst", max_length=60)
    greeting: str = Field(default="", max_length=300)
    persona: str = Field(default="", max_length=800)
    default_language: str = Field(default="zh-CN", max_length=40)
    voice_name: str = Field(default="default", max_length=80)
    portrait_data_url: str | None = None
    motion_mode: Literal["portrait_motion", "studio_card"] = "portrait_motion"
    tts_backend: Literal["browser", "local_server"] = "browser"
    asr_backend: Literal["browser", "manual"] = "browser"
    note: str | None = None
    updated_at: str = ""
