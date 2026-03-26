from __future__ import annotations

from fastapi import HTTPException, Request

from app.schemas_v2 import AuthUser


def read_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "").strip()
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def require_current_user(request: Request) -> AuthUser:
    auth_store = request.app.state.container.auth_store
    user = auth_store.get_user_by_token(read_bearer_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录。")
    return user
