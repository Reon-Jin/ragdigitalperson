from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.schemas_v2 import UserProfile
from app.storage.database import Database


class ProfileStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = self.settings.data_dir / "profiles.json"
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()
        self._bootstrap_legacy_json()

    def get(self, profile_id: str = "default") -> UserProfile:
        row = self.db.fetchone(
            """
            SELECT profile_id, risk_level, investment_horizon, markets_json, sector_preferences_json, style_preference
            FROM user_profiles
            WHERE profile_id = %(profile_id)s
            """,
            {"profile_id": profile_id},
        )
        if not row:
            return UserProfile(profile_id=profile_id)
        return UserProfile(
            profile_id=profile_id,
            risk_level=str(row.get("risk_level") or "medium"),
            investment_horizon=str(row.get("investment_horizon") or "medium"),
            markets=list(json.loads(row.get("markets_json") or "[]") or ["A-share"]),
            sector_preferences=list(json.loads(row.get("sector_preferences_json") or "[]")),
            style_preference=str(row.get("style_preference") or "advisor"),
        )

    def put(self, profile_id: str, profile: UserProfile) -> UserProfile:
        normalized = profile.model_copy(update={"profile_id": profile_id})
        payload = {
            "profile_id": profile_id,
            "risk_level": normalized.risk_level,
            "investment_horizon": normalized.investment_horizon,
            "markets_json": json.dumps(normalized.markets, ensure_ascii=False),
            "sector_preferences_json": json.dumps(normalized.sector_preferences, ensure_ascii=False),
            "style_preference": normalized.style_preference,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.db.upsert("user_profiles", payload, conflict_keys=["profile_id"])
        return normalized

    def _bootstrap_legacy_json(self) -> None:
        existing = self.db.scalar("SELECT COUNT(*) AS count FROM user_profiles", default=0)
        if int(existing or 0) > 0 or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        for profile_id, raw in payload.items():
            try:
                profile = UserProfile(**dict(raw or {}, profile_id=profile_id))
            except Exception:
                continue
            self.put(profile_id, profile)
