from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from app.config import Settings
from app.schemas_v2 import ConversationMessage, ConversationSession, ConversationSummary
from app.storage.database import Database


class ConversationStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = self.settings.data_dir / "conversations.json"
        self.db = Database(settings.database_url, settings.app_db_path)
        self.db.init_schema()
        self._lock = threading.RLock()
        self._bootstrap_legacy_json()

    def list_summaries(self, user_id: str) -> list[ConversationSummary]:
        rows = self.db.fetchall(
            """
            SELECT conversation_id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = %(user_id)s
            ORDER BY updated_at DESC
            """,
            {"user_id": user_id},
        )
        result: list[ConversationSummary] = []
        for row in rows:
            message_count = int(
                self.db.scalar(
                    "SELECT COUNT(*) AS count FROM conversation_messages WHERE conversation_id = %(conversation_id)s",
                    {"conversation_id": row["conversation_id"]},
                    default=0,
                )
                or 0
            )
            last_row = self.db.fetchone(
                """
                SELECT content
                FROM conversation_messages
                WHERE conversation_id = %(conversation_id)s
                ORDER BY created_at DESC, message_id DESC
                """,
                {"conversation_id": row["conversation_id"]},
            )
            preview = None
            if last_row and str(last_row.get("content") or "").strip():
                preview = str(last_row["content"]).replace("\n", " ").strip()[:64]
            result.append(
                ConversationSummary(
                    conversation_id=row["conversation_id"],
                    title=row.get("title") or "新对话",
                    created_at=row["created_at"],
                    updated_at=row.get("updated_at") or row["created_at"],
                    message_count=message_count,
                    last_message_preview=preview,
                )
            )
        return result

    def get(self, user_id: str, conversation_id: str) -> ConversationSession | None:
        conversation = self.db.fetchone(
            """
            SELECT conversation_id, user_id, title, created_at, updated_at
            FROM conversations
            WHERE conversation_id = %(conversation_id)s
            """,
            {"conversation_id": conversation_id},
        )
        if not conversation or conversation.get("user_id") != user_id:
            return None
        return self._session_from_row(conversation)

    def create(self, user_id: str, title: str | None = None, conversation_id: str | None = None) -> ConversationSession:
        with self._lock:
            conversation_id = conversation_id or self._new_id()
            existing = self.db.fetchone(
                """
                SELECT conversation_id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )
            if existing is None:
                now = self._now()
                record = {
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "title": self._normalize_title(title) or "新对话",
                    "created_at": now,
                    "updated_at": now,
                }
                self.db.execute(
                    """
                    INSERT INTO conversations (conversation_id, user_id, title, created_at, updated_at)
                    VALUES (%(conversation_id)s, %(user_id)s, %(title)s, %(created_at)s, %(updated_at)s)
                    """,
                    record,
                )
                return self._session_from_row(record)
            if existing.get("user_id") != user_id:
                raise ValueError("Conversation belongs to another user.")
            return self._session_from_row(existing)

    def ensure(self, user_id: str, conversation_id: str | None = None) -> ConversationSession:
        if conversation_id:
            existing = self.get(user_id, conversation_id)
            if existing is not None:
                return existing
            return self.create(user_id, conversation_id=conversation_id)
        return self.create(user_id)

    def delete(self, user_id: str, conversation_id: str) -> bool:
        with self._lock:
            conversation = self.db.fetchone(
                "SELECT user_id FROM conversations WHERE conversation_id = %(conversation_id)s",
                {"conversation_id": conversation_id},
            )
            if not conversation or conversation.get("user_id") != user_id:
                return False
            self.db.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = %(conversation_id)s",
                {"conversation_id": conversation_id},
            )
            self.db.execute(
                "DELETE FROM conversations WHERE conversation_id = %(conversation_id)s",
                {"conversation_id": conversation_id},
            )
            return True

    def rename(self, user_id: str, conversation_id: str, title: str) -> ConversationSession | None:
        normalized = self._normalize_title(title)
        if not normalized:
            return None
        with self._lock:
            conversation = self.db.fetchone(
                """
                SELECT conversation_id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )
            if not conversation or conversation.get("user_id") != user_id:
                return None
            updated_at = self._now()
            self.db.execute(
                """
                UPDATE conversations
                SET title = %(title)s, updated_at = %(updated_at)s
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id, "title": normalized, "updated_at": updated_at},
            )
            conversation["title"] = normalized
            conversation["updated_at"] = updated_at
            return self._session_from_row(conversation)

    def append_message(
        self,
        user_id: str,
        conversation_id: str,
        *,
        role: str,
        content: str,
        task_type: str | None = None,
        route: dict | None = None,
    ) -> ConversationSession:
        text = str(content or "").strip()
        if not text:
            session = self.get(user_id, conversation_id)
            return session if session is not None else self.ensure(user_id, conversation_id)

        with self._lock:
            conversation = self.db.fetchone(
                """
                SELECT conversation_id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id},
            )
            if conversation is None:
                conversation = self.create(user_id, conversation_id=conversation_id).model_dump()
            elif conversation.get("user_id") != user_id:
                raise ValueError("Conversation belongs to another user.")

            if role == "user" and (not conversation.get("title") or conversation.get("title") == "新对话"):
                conversation["title"] = self._build_title(text)

            updated_at = self._now()
            self.db.execute(
                """
                INSERT INTO conversation_messages (message_id, conversation_id, user_id, role, content, created_at, task_type, route_json)
                VALUES (%(message_id)s, %(conversation_id)s, %(user_id)s, %(role)s, %(content)s, %(created_at)s, %(task_type)s, %(route_json)s)
                """,
                {
                    "message_id": self._new_id(),
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "role": role,
                    "content": text,
                    "created_at": updated_at,
                    "task_type": task_type,
                    "route_json": json.dumps(route, ensure_ascii=False) if route else None,
                },
            )
            self.db.execute(
                """
                UPDATE conversations
                SET title = %(title)s, updated_at = %(updated_at)s
                WHERE conversation_id = %(conversation_id)s
                """,
                {"conversation_id": conversation_id, "title": conversation["title"], "updated_at": updated_at},
            )
            conversation["updated_at"] = updated_at
            return self._session_from_row(conversation)

    def _session_from_row(self, payload: dict) -> ConversationSession:
        messages = self.db.fetchall(
            """
            SELECT message_id, role, content, created_at, task_type, route_json
            FROM conversation_messages
            WHERE conversation_id = %(conversation_id)s
            ORDER BY created_at ASC, message_id ASC
            """,
            {"conversation_id": payload["conversation_id"]},
        )
        return ConversationSession(
            conversation_id=payload["conversation_id"],
            title=payload.get("title") or "新对话",
            created_at=payload["created_at"],
            updated_at=payload.get("updated_at") or payload["created_at"],
            messages=[
                ConversationMessage(
                    message_id=item["message_id"],
                    role=item["role"],
                    content=item["content"],
                    created_at=item["created_at"],
                    task_type=item.get("task_type"),
                    route=self._loads(item.get("route_json")),
                )
                for item in messages
            ],
        )

    def _bootstrap_legacy_json(self) -> None:
        if not self.path.exists():
            return
        existing = self.db.scalar("SELECT COUNT(*) AS count FROM conversations", default=0)
        if int(existing or 0) > 0:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        for conversation_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            user_id = str(item.get("user_id") or "").strip()
            created_at = str(item.get("created_at") or self._now())
            updated_at = str(item.get("updated_at") or created_at)
            title = str(item.get("title") or "新对话")
            if not user_id:
                continue
            self.db.execute(
                """
                INSERT INTO conversations (conversation_id, user_id, title, created_at, updated_at)
                VALUES (%(conversation_id)s, %(user_id)s, %(title)s, %(created_at)s, %(updated_at)s)
                """,
                {
                    "conversation_id": str(item.get("conversation_id") or conversation_id),
                    "user_id": user_id,
                    "title": title,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )
            for message in item.get("messages", []):
                if not isinstance(message, dict):
                    continue
                self.db.execute(
                    """
                    INSERT INTO conversation_messages (message_id, conversation_id, user_id, role, content, created_at, task_type, route_json)
                    VALUES (%(message_id)s, %(conversation_id)s, %(user_id)s, %(role)s, %(content)s, %(created_at)s, %(task_type)s, %(route_json)s)
                    """,
                    {
                        "message_id": str(message.get("message_id") or self._new_id()),
                        "conversation_id": str(item.get("conversation_id") or conversation_id),
                        "user_id": user_id,
                        "role": str(message.get("role") or "assistant"),
                        "content": str(message.get("content") or ""),
                        "created_at": str(message.get("created_at") or updated_at),
                        "task_type": message.get("task_type"),
                        "route_json": json.dumps(message.get("route"), ensure_ascii=False) if message.get("route") else None,
                    },
                )

    def _normalize_title(self, title: str | None) -> str | None:
        normalized = str(title or "").strip()
        return normalized[:60] if normalized else None

    def _build_title(self, content: str) -> str:
        compact = " ".join(str(content).split())
        return compact[:24] or "新对话"

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _now(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _loads(self, value: str | None) -> dict | None:
        if not value:
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
