from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import datetime
from typing import Any

from app.config import Settings
from app.schemas_v2 import AgentMemorySnapshot
from app.storage.database import Database


class AgentMemoryStore:
    _SYMBOL_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)?(\d{6})\b", re.IGNORECASE)
    _SECTOR_TERMS = ("红利", "半导体", "AI", "算力", "新能源", "医药", "消费", "券商", "银行", "军工", "黄金")
    _STYLE_TERMS = {
        "低风险": ("稳健", "低波动", "防御", "回撤小"),
        "平衡配置": ("均衡", "分散", "平衡"),
        "进攻成长": ("高弹性", "成长", "进攻", "景气"),
        "高股息": ("高股息", "红利", "股息"),
        "短线交易": ("短线", "日内", "波段"),
        "长期持有": ("长期", "长期持有", "三年", "五年"),
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = self.settings.data_dir / "agent_memories.json"
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()
        self._lock = threading.RLock()
        self._bootstrap_legacy_json()

    def get(self, user_id: str) -> AgentMemorySnapshot:
        payload = self._load_state(user_id)
        return AgentMemorySnapshot(
            user_id=user_id,
            summary=self._build_summary(payload),
            recent_symbols=list(payload.get("recent_symbols", []))[:6],
            recent_sectors=list(payload.get("recent_sectors", []))[:6],
            preference_tags=list(payload.get("preference_tags", []))[:8],
            recent_tasks=list(payload.get("recent_tasks", []))[:6],
            recent_actions=list(payload.get("recent_actions", []))[:8],
            updated_at=str(payload.get("updated_at") or self._now()),
        )

    def record_interaction(
        self,
        user_id: str,
        *,
        role: str,
        content: str,
        route: dict[str, Any] | None = None,
    ) -> AgentMemorySnapshot:
        with self._lock:
            state = self._load_state(user_id)
            route = route or {}
            if role == "user":
                self._merge_symbols(state, self._extract_symbols(content), limit=8)
                self._merge_tags(state, self._extract_sectors(content), field="recent_sectors", limit=8)
                self._merge_tags(state, self._extract_style_tags(content), field="preference_tags", limit=10)
                self._push_recent(state, "recent_actions", self._normalize_action(content), limit=8)
            task_type = route.get("task_type")
            if task_type:
                self._push_recent(state, "recent_tasks", str(task_type), limit=8)
            if route.get("symbol"):
                self._merge_symbols(state, [str(route["symbol"])], limit=8)
            if route.get("sector"):
                self._merge_tags(state, [str(route["sector"])], field="recent_sectors", limit=8)
            state["updated_at"] = self._now()
            self._save_state(user_id, state)
        return self.get(user_id)

    def record_event(
        self,
        user_id: str,
        *,
        event_type: str,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentMemorySnapshot:
        with self._lock:
            state = self._load_state(user_id)
            metadata = metadata or {}
            action = summary.strip() or self._format_event_label(event_type, metadata)
            self._push_recent(state, "recent_actions", action, limit=8)
            if metadata.get("task_type"):
                self._push_recent(state, "recent_tasks", str(metadata["task_type"]), limit=8)
            if metadata.get("symbol"):
                self._merge_symbols(state, [str(metadata["symbol"])], limit=8)
            if metadata.get("sector"):
                self._merge_tags(state, [str(metadata["sector"])], field="recent_sectors", limit=8)
            if metadata.get("profile_tags"):
                self._merge_tags(state, list(metadata["profile_tags"]), field="preference_tags", limit=10)
            state["updated_at"] = self._now()
            self._save_state(user_id, state)
        return self.get(user_id)

    def record_profile(self, user_id: str, *, risk_level: str, investment_horizon: str, sectors: list[str]) -> AgentMemorySnapshot:
        tags = [f"风险:{risk_level}", f"期限:{investment_horizon}", *[f"偏好:{item}" for item in sectors if item]]
        return self.record_event(
            user_id,
            event_type="profile_update",
            summary="更新了风险偏好和关注方向",
            metadata={"profile_tags": tags, "sector": sectors[0] if sectors else None},
        )

    def _load_state(self, user_id: str) -> dict[str, Any]:
        row = self.db.fetchone(
            """
            SELECT summary, recent_symbols_json, recent_sectors_json, preference_tags_json, recent_tasks_json, recent_actions_json, updated_at
            FROM agent_memories
            WHERE user_id = %(user_id)s
            """,
            {"user_id": user_id},
        )
        if not row:
            return {}
        return {
            "summary": str(row.get("summary") or ""),
            "recent_symbols": self._loads(row.get("recent_symbols_json")),
            "recent_sectors": self._loads(row.get("recent_sectors_json")),
            "preference_tags": self._loads(row.get("preference_tags_json")),
            "recent_tasks": self._loads(row.get("recent_tasks_json")),
            "recent_actions": self._loads(row.get("recent_actions_json")),
            "updated_at": str(row.get("updated_at") or self._now()),
        }

    def _save_state(self, user_id: str, state: dict[str, Any]) -> None:
        payload = {
            "user_id": user_id,
            "summary": self._build_summary(state),
            "recent_symbols_json": json.dumps(state.get("recent_symbols", []), ensure_ascii=False),
            "recent_sectors_json": json.dumps(state.get("recent_sectors", []), ensure_ascii=False),
            "preference_tags_json": json.dumps(state.get("preference_tags", []), ensure_ascii=False),
            "recent_tasks_json": json.dumps(state.get("recent_tasks", []), ensure_ascii=False),
            "recent_actions_json": json.dumps(state.get("recent_actions", []), ensure_ascii=False),
            "updated_at": str(state.get("updated_at") or self._now()),
        }
        self.db.upsert("agent_memories", payload, conflict_keys=["user_id"])

    def _bootstrap_legacy_json(self) -> None:
        if not self.path.exists():
            return
        existing = self.db.scalar("SELECT COUNT(*) AS count FROM agent_memories", default=0)
        if int(existing or 0) > 0:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        for user_id, state in payload.items():
            if not isinstance(state, dict):
                continue
            normalized = {
                "recent_symbols": [str(item) for item in state.get("recent_symbols", []) if str(item).strip()],
                "recent_sectors": [str(item) for item in state.get("recent_sectors", []) if str(item).strip()],
                "preference_tags": [str(item) for item in state.get("preference_tags", []) if str(item).strip()],
                "recent_tasks": [str(item) for item in state.get("recent_tasks", []) if str(item).strip()],
                "recent_actions": [str(item) for item in state.get("recent_actions", []) if str(item).strip()],
                "updated_at": str(state.get("updated_at") or self._now()),
            }
            self._save_state(str(user_id), normalized)

    def _build_summary(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        if payload.get("preference_tags"):
            parts.append("偏好：" + "、".join(payload["preference_tags"][:4]))
        if payload.get("recent_symbols"):
            parts.append("最近关注股票：" + "、".join(payload["recent_symbols"][:4]))
        if payload.get("recent_sectors"):
            parts.append("最近关注方向：" + "、".join(payload["recent_sectors"][:4]))
        if payload.get("recent_tasks"):
            task_counts = Counter(payload["recent_tasks"][:6])
            parts.append("常用模块：" + "、".join(item for item, _ in task_counts.most_common(3)))
        if payload.get("recent_actions"):
            parts.append("最近动作：" + "；".join(payload["recent_actions"][:3]))
        return " | ".join(parts) if parts else "暂未形成稳定偏好，需要继续通过对话和操作学习。"

    def _extract_symbols(self, text: str) -> list[str]:
        return list(dict.fromkeys(match.group(1) for match in self._SYMBOL_PATTERN.finditer(str(text or ""))))

    def _extract_sectors(self, text: str) -> list[str]:
        return [item for item in self._SECTOR_TERMS if item in str(text or "")]

    def _extract_style_tags(self, text: str) -> list[str]:
        lowered = str(text or "")
        result: list[str] = []
        for label, terms in self._STYLE_TERMS.items():
            if any(term in lowered for term in terms):
                result.append(label)
        return result

    def _normalize_action(self, content: str) -> str:
        compact = " ".join(str(content or "").split())
        return compact[:42] if compact else "触发了一次交互"

    def _format_event_label(self, event_type: str, metadata: dict[str, Any]) -> str:
        mapping = {
            "view_security": f"查看了 {metadata.get('symbol') or metadata.get('query') or '个股'} 详情",
            "switch_module": f"切换到 {metadata.get('task_type') or '新模块'}",
            "profile_update": "更新了用户画像",
        }
        return mapping.get(event_type, event_type)

    def _merge_symbols(self, state: dict[str, Any], symbols: list[str], *, limit: int) -> None:
        self._merge_tags(state, symbols, field="recent_symbols", limit=limit)

    def _merge_tags(self, state: dict[str, Any], values: list[str], *, field: str, limit: int) -> None:
        existing = [str(item) for item in state.get(field, []) if str(item).strip()]
        for value in values:
            text = str(value or "").strip()
            if text and text not in existing:
                existing.insert(0, text)
        state[field] = existing[:limit]

    def _push_recent(self, state: dict[str, Any], field: str, value: str, *, limit: int) -> None:
        normalized = str(value or "").strip()
        if not normalized:
            return
        existing = [item for item in state.get(field, []) if item != normalized]
        state[field] = [normalized, *existing][:limit]

    def _loads(self, value: str | None) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if str(item).strip()]

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
