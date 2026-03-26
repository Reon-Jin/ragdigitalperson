from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.schemas_v2 import AuthUser
from app.storage.database import Database


class AuthStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users_path = self.settings.data_dir / "users.json"
        self.sessions_path = self.settings.data_dir / "sessions.json"
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()
        self._lock = threading.RLock()
        self._bootstrap_legacy_json()

    def register(self, username: str, password: str, display_name: str | None = None) -> tuple[AuthUser, str]:
        normalized_username = self._normalize_username(username)
        normalized_display_name = self._normalize_display_name(display_name or username)
        self._validate_password(password)

        with self._lock:
            existing = self.db.fetchone(
                "SELECT user_id FROM users WHERE lower(username) = lower(%(username)s)",
                {"username": normalized_username},
            )
            if existing:
                raise ValueError("用户名已存在")

            user_id = uuid.uuid4().hex[:12]
            now = self._now()
            user_record = {
                "user_id": user_id,
                "username": normalized_username,
                "display_name": normalized_display_name,
                "password_hash": self._hash_password(password),
                "created_at": now,
                "last_login_at": now,
            }
            self.db.execute(
                """
                INSERT INTO users (user_id, username, display_name, password_hash, created_at, last_login_at)
                VALUES (%(user_id)s, %(username)s, %(display_name)s, %(password_hash)s, %(created_at)s, %(last_login_at)s)
                """,
                user_record,
            )
            token = self._create_session_unlocked(user_id)
            return self._to_auth_user(user_record), token

    def login(self, username: str, password: str) -> tuple[AuthUser, str]:
        normalized_username = self._normalize_username(username)
        with self._lock:
            user_record = self.db.fetchone(
                "SELECT user_id, username, display_name, password_hash, created_at, last_login_at FROM users WHERE lower(username) = lower(%(username)s)",
                {"username": normalized_username},
            )
            if user_record is None or not self._verify_password(password, str(user_record.get("password_hash", ""))):
                raise ValueError("用户名或密码错误")

            user_record["last_login_at"] = self._now()
            self.db.execute(
                "UPDATE users SET last_login_at = %(last_login_at)s WHERE user_id = %(user_id)s",
                {"user_id": user_record["user_id"], "last_login_at": user_record["last_login_at"]},
            )
            token = self._create_session_unlocked(user_record["user_id"])
            return self._to_auth_user(user_record), token

    def get_user_by_token(self, token: str | None) -> AuthUser | None:
        if not token:
            return None
        with self._lock:
            session = self.db.fetchone(
                "SELECT token, user_id, created_at, expires_at FROM user_sessions WHERE token = %(token)s",
                {"token": token},
            )
            if session is None:
                return None
            expires_at = self._parse_time(session.get("expires_at"))
            if expires_at is None or expires_at <= datetime.now(timezone.utc):
                self.db.execute("DELETE FROM user_sessions WHERE token = %(token)s", {"token": token})
                return None
            user_record = self.db.fetchone(
                "SELECT user_id, username, display_name, created_at, last_login_at FROM users WHERE user_id = %(user_id)s",
                {"user_id": session.get("user_id")},
            )
            if user_record is None:
                self.db.execute("DELETE FROM user_sessions WHERE token = %(token)s", {"token": token})
                return None
            return self._to_auth_user(user_record)

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self.db.execute("DELETE FROM user_sessions WHERE token = %(token)s", {"token": token})

    def get_user(self, user_id: str) -> AuthUser | None:
        row = self.db.fetchone(
            "SELECT user_id, username, display_name, created_at, last_login_at FROM users WHERE user_id = %(user_id)s",
            {"user_id": user_id},
        )
        return self._to_auth_user(row) if row else None

    def _create_session_unlocked(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        payload = {
            "token": token,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
        }
        self.db.execute(
            """
            INSERT INTO user_sessions (token, user_id, created_at, expires_at)
            VALUES (%(token)s, %(user_id)s, %(created_at)s, %(expires_at)s)
            """,
            payload,
        )
        return token

    def _bootstrap_legacy_json(self) -> None:
        with self._lock:
            existing = self.db.scalar("SELECT COUNT(*) AS count FROM users", default=0)
            if int(existing or 0) > 0:
                return
            users = self._load_legacy_payload(self.users_path)
            sessions = self._load_legacy_payload(self.sessions_path)
            for user_id, payload in users.items():
                if not isinstance(payload, dict):
                    continue
                record = {
                    "user_id": str(payload.get("user_id") or user_id),
                    "username": str(payload.get("username") or ""),
                    "display_name": str(payload.get("display_name") or payload.get("username") or "用户"),
                    "password_hash": str(payload.get("password_hash") or ""),
                    "created_at": str(payload.get("created_at") or self._now()),
                    "last_login_at": str(payload.get("last_login_at") or payload.get("created_at") or self._now()),
                }
                if not record["username"] or not record["password_hash"]:
                    continue
                self.db.execute(
                    """
                    INSERT INTO users (user_id, username, display_name, password_hash, created_at, last_login_at)
                    VALUES (%(user_id)s, %(username)s, %(display_name)s, %(password_hash)s, %(created_at)s, %(last_login_at)s)
                    """,
                    record,
                )
            for token, payload in sessions.items():
                if not isinstance(payload, dict):
                    continue
                record = {
                    "token": str(token),
                    "user_id": str(payload.get("user_id") or ""),
                    "created_at": str(payload.get("created_at") or self._now()),
                    "expires_at": str(payload.get("expires_at") or self._now()),
                }
                if not record["user_id"]:
                    continue
                self.db.execute(
                    """
                    INSERT INTO user_sessions (token, user_id, created_at, expires_at)
                    VALUES (%(token)s, %(user_id)s, %(created_at)s, %(expires_at)s)
                    """,
                    record,
                )

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000)
        return f"{salt}${derived.hex()}"

    def _verify_password(self, password: str, payload: str) -> bool:
        if "$" not in payload:
            return False
        salt, _, digest = payload.partition("$")
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000).hex()
        return hmac.compare_digest(derived, digest)

    def _validate_password(self, password: str) -> None:
        if len(str(password or "")) < 6:
            raise ValueError("密码长度至少 6 位")

    def _normalize_username(self, username: str) -> str:
        normalized = "".join(str(username or "").strip().split())
        if len(normalized) < 3:
            raise ValueError("用户名至少 3 个字符")
        return normalized[:40]

    def _normalize_display_name(self, display_name: str) -> str:
        normalized = str(display_name or "").strip()
        return (normalized or "用户")[:40]

    def _to_auth_user(self, payload: dict | None) -> AuthUser:
        if payload is None:
            raise ValueError("user payload is required")
        return AuthUser(
            user_id=str(payload.get("user_id") or ""),
            username=str(payload.get("username") or ""),
            display_name=str(payload.get("display_name") or payload.get("username") or "用户"),
            created_at=str(payload.get("created_at") or self._now()),
            last_login_at=str(payload.get("last_login_at") or payload.get("created_at") or self._now()),
        )

    def _load_legacy_payload(self, path: Path) -> dict[str, dict]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
