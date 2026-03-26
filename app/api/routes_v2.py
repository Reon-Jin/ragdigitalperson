from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.auth import read_bearer_token, require_current_user
from app.market_data.schemas.quote import PrefetchResponse
from app.market_data.schemas.screening import RecommendationRequest
from app.schemas_v2 import (
    AgentEventRequest,
    AuthResponse,
    CreateConversationRequest,
    HybridCopilotRequest,
    LocalAvatarProfile,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    UserProfile,
)


router = APIRouter(prefix="/api/v2", tags=["finavatar-v2"])


@router.post("/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest, request: Request) -> AuthResponse:
    auth_store = request.app.state.container.auth_store
    try:
        user, token = auth_store.register(payload.username, payload.password, payload.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthResponse(token=token, user=user)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request) -> AuthResponse:
    auth_store = request.app.state.container.auth_store
    try:
        user, token = auth_store.login(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return AuthResponse(token=token, user=user)


@router.post("/auth/logout")
async def logout(request: Request) -> dict:
    request.app.state.container.auth_store.logout(read_bearer_token(request))
    return {"ok": True}


@router.get("/auth/session", response_model=SessionResponse)
async def session(request: Request) -> SessionResponse:
    user = request.app.state.container.auth_store.get_user_by_token(read_bearer_token(request))
    return SessionResponse(authenticated=user is not None, user=user)


@router.get("/avatar/profile", response_model=LocalAvatarProfile)
async def avatar_profile(request: Request) -> LocalAvatarProfile:
    user = require_current_user(request)
    profile = request.app.state.avatar_service.get(user.user_id)
    return LocalAvatarProfile(**profile)


@router.put("/avatar/profile", response_model=LocalAvatarProfile)
async def update_avatar_profile(payload: LocalAvatarProfile, request: Request) -> LocalAvatarProfile:
    user = require_current_user(request)
    profile = request.app.state.avatar_service.put(user.user_id, payload.model_dump())
    return LocalAvatarProfile(**profile)


@router.get("/agent/memory")
async def agent_memory(request: Request) -> dict:
    user = require_current_user(request)
    memory = request.app.state.container.agent_memory_store.get(user.user_id)
    return memory.model_dump()


@router.post("/agent/events")
async def record_agent_event(payload: AgentEventRequest, request: Request) -> dict:
    user = require_current_user(request)
    memory = request.app.state.container.agent_memory_store.record_event(
        user.user_id,
        event_type=payload.event_type,
        summary=payload.summary,
        metadata=payload.metadata,
    )
    return memory.model_dump()


@router.get("/conversations")
async def list_conversations(request: Request) -> list[dict]:
    user = require_current_user(request)
    store = request.app.state.container.conversation_store
    return [item.model_dump() for item in store.list_summaries(user.user_id)]


@router.post("/conversations")
async def create_conversation(payload: CreateConversationRequest, request: Request) -> dict:
    user = require_current_user(request)
    store = request.app.state.container.conversation_store
    return store.create(user.user_id, title=payload.title).model_dump()


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict:
    user = require_current_user(request)
    store = request.app.state.container.conversation_store
    session = store.get(user.user_id, conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return session.model_dump()


@router.put("/conversations/{conversation_id}")
async def rename_conversation(conversation_id: str, payload: CreateConversationRequest, request: Request) -> dict:
    user = require_current_user(request)
    store = request.app.state.container.conversation_store
    session = store.rename(user.user_id, conversation_id, payload.title or "")
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found or title is empty.")
    return session.model_dump()


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict:
    user = require_current_user(request)
    store = request.app.state.container.conversation_store
    if not store.delete(user.user_id, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True, "conversation_id": conversation_id}


@router.post("/copilot/stream")
async def copilot_stream(payload: HybridCopilotRequest, request: Request) -> StreamingResponse:
    user = require_current_user(request)
    container = request.app.state.container
    engine = container.hybrid_answer_engine
    conversation_store = container.conversation_store
    memory_store = container.agent_memory_store
    conversation = conversation_store.ensure(user.user_id, payload.conversation_id)
    effective_payload = payload.model_copy(
        update={
            "conversation_id": conversation.conversation_id,
            "profile_id": user.user_id,
            "user_id": user.user_id,
        }
    )

    async def event_stream():
        accumulated_answer = ""
        final_route = None
        assistant_saved = False
        try:
            session = conversation_store.append_message(
                user.user_id,
                conversation.conversation_id,
                role="user",
                content=effective_payload.message,
                task_type=effective_payload.task_type,
            )
            memory_store.record_interaction(
                user.user_id,
                role="user",
                content=effective_payload.message,
                route={"task_type": effective_payload.task_type},
            )
            yield f"data: {json.dumps({'type': 'conversation', 'conversation': {'conversation_id': session.conversation_id, 'title': session.title}}, ensure_ascii=False)}\n\n"
            async for event in engine.stream(effective_payload):
                if event.get("type") == "delta":
                    accumulated_answer += event.get("delta") or ""
                elif event.get("type") == "final":
                    accumulated_answer = event.get("answer") or accumulated_answer
                    final_route = event.get("route")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if accumulated_answer.strip():
                conversation_store.append_message(
                    user.user_id,
                    conversation.conversation_id,
                    role="assistant",
                    content=accumulated_answer,
                    task_type=(final_route or {}).get("task_type"),
                    route=final_route,
                )
                memory_store.record_interaction(
                    user.user_id,
                    role="assistant",
                    content=accumulated_answer,
                    route=final_route,
                )
                assistant_saved = True
        except Exception as exc:
            if not assistant_saved and accumulated_answer.strip():
                conversation_store.append_message(
                    user.user_id,
                    conversation.conversation_id,
                    role="assistant",
                    content=accumulated_answer,
                    task_type=(final_route or {}).get("task_type"),
                    route=final_route,
                )
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/profile", response_model=UserProfile)
async def get_profile(request: Request) -> UserProfile:
    user = require_current_user(request)
    return request.app.state.container.profile_store.get(user.user_id)


@router.put("/profile", response_model=UserProfile)
async def update_profile(payload: UserProfile, request: Request) -> UserProfile:
    user = require_current_user(request)
    profile = request.app.state.container.profile_store.put(user.user_id, payload)
    request.app.state.container.agent_memory_store.record_profile(
        user.user_id,
        risk_level=profile.risk_level,
        investment_horizon=profile.investment_horizon,
        sectors=profile.sector_preferences,
    )
    return profile


@router.get("/dashboard/overview")
async def dashboard_overview(request: Request, market: str | None = None) -> dict:
    require_current_user(request)
    overview = await request.app.state.container.dashboard_api.overview(market=market)
    return overview.model_dump()


@router.get("/health/market")
async def market_health(request: Request) -> dict:
    require_current_user(request)
    providers = request.app.state.container.market_registry.all_providers()
    checks = []
    for provider in providers:
        try:
            health = await asyncio.wait_for(provider.healthcheck(), timeout=0.35)
        except Exception as exc:
            health = {"provider": getattr(provider, "provider_name", "unknown"), "ok": False, "latency_ms": None, "error": str(exc)}
        if hasattr(health, "model_dump"):
            health = health.model_dump()
        checks.append(health)
    return {
        "status": "ok" if any(item["ok"] for item in checks) else "degraded",
        "providers": checks,
    }


@router.get("/quote/{symbol}")
async def quote_detail(symbol: str, request: Request, market: str | None = None) -> dict:
    require_current_user(request)
    result = await request.app.state.container.quote_api.get_quote(symbol, market=market)
    return result.model_dump()


@router.get("/stocks/query")
async def stock_detail_by_query(query: str, request: Request, market: str | None = None) -> dict:
    user = require_current_user(request)
    resolver = request.app.state.container.stock_resolver
    resolved = await resolver.resolve(query)
    if resolved is None:
        symbol = resolver.extract_symbol(query)
        if not symbol:
            raise HTTPException(status_code=404, detail="未识别到 A 股股票代码或名称。")
        resolved_symbol = symbol
    else:
        resolved_symbol = resolved.symbol
    request.app.state.container.agent_memory_store.record_event(
        user.user_id,
        event_type="view_security",
        summary=f"查看了 {query} 的个股详情",
        metadata={"symbol": resolved_symbol},
    )
    result = await request.app.state.container.stock_api.analyze(resolved_symbol, market=market)
    return result.model_dump()


@router.get("/stocks/{symbol}")
async def stock_detail(symbol: str, request: Request, market: str | None = None) -> dict:
    require_current_user(request)
    result = await request.app.state.container.stock_api.analyze(symbol, market=market)
    return result.model_dump()


@router.get("/funds/screen")
async def fund_screen(query: str, request: Request, risk_level: str = "medium", market: str | None = None, limit: int = 5) -> dict:
    require_current_user(request)
    result = await request.app.state.container.fund_api.screen(query, risk_level=risk_level, market=market, limit=limit)
    return result.model_dump()


@router.get("/funds/{fund_code}")
async def fund_detail(fund_code: str, request: Request, market: str | None = None) -> dict:
    require_current_user(request)
    result = await request.app.state.container.fund_api.analyze(fund_code, market=market)
    return result.model_dump()


@router.post("/recommendations/stocks")
async def recommend_stocks(payload: RecommendationRequest, request: Request) -> dict:
    require_current_user(request)
    result = await request.app.state.container.recommendation_api.recommend_stocks(payload)
    return result.model_dump()


@router.post("/prefetch/security")
async def prefetch_security(payload: PrefetchResponse, request: Request, market: str | None = None) -> dict:
    require_current_user(request)
    completed: list[str] = []
    if "quote" in payload.tasks:
        await request.app.state.container.quote_service.get_snapshot(payload.symbol, market=market)
        completed.append("quote")
    if "fundamentals" in payload.tasks:
        await request.app.state.container.fundamentals_service.get_profile(payload.symbol, market=market)
        completed.append("fundamentals")
    if "news" in payload.tasks:
        await request.app.state.container.news_service.get_news(symbol=payload.symbol, limit=3)
        completed.append("news")
    return PrefetchResponse(symbol=payload.symbol, tasks=payload.tasks, completed=completed).model_dump()