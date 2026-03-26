from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.storage.database import Database


class LocalAvatarService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_dir = settings.data_dir / "avatar_profiles"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()
        self._bootstrap_legacy_files()

    def get(self, user_id: str) -> dict[str, Any]:
        row = self.db.fetchone(
            "SELECT payload_json FROM avatar_profiles WHERE user_id = %(user_id)s",
            {"user_id": user_id},
        )
        if not row:
            profile = self.default_profile(user_id)
            self.put(user_id, profile)
            return profile
        return {**self.default_profile(user_id), **self._loads(row.get("payload_json"))}

    def put(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.default_profile(user_id)
        profile = {**current, **payload, "updated_at": self._now()}
        self.db.upsert(
            "avatar_profiles",
            {
                "user_id": user_id,
                "payload_json": json.dumps(profile, ensure_ascii=False),
                "updated_at": profile["updated_at"],
            },
            conflict_keys=["user_id"],
        )
        return profile

    def default_profile(self, user_id: str) -> dict[str, Any]:
        return {
            "avatar_id": f"local-{user_id}",
            "display_name": "FinAvatar Analyst",
            "greeting": "你好，我会结合你的长期偏好、实时行情和私有知识库给出分析。",
            "persona": "专业、克制、可解释的金融研究助理。",
            "default_language": "zh-CN",
            "voice_name": "default",
            "portrait_data_url": None,
            "motion_mode": "portrait_motion",
            "tts_backend": "browser",
            "asr_backend": "browser",
            "note": "当前为本地自建头像模式：头像渲染、播报和语音输入优先使用本机浏览器能力，后续可扩展接入本地 LivePortrait / MuseTalk / Faster-Whisper。",
            "updated_at": self._now(),
        }

    def _bootstrap_legacy_files(self) -> None:
        existing = self.db.scalar("SELECT COUNT(*) AS count FROM avatar_profiles", default=0)
        if int(existing or 0) > 0 or not self.base_dir.exists():
            return
        for path in self.base_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            user_id = path.stem
            if not user_id:
                continue
            self.put(user_id, payload if isinstance(payload, dict) else {})

    def _loads(self, payload: str | None) -> dict[str, Any]:
        if not payload:
            return {}
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
