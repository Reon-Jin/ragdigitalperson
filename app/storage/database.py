from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, unquote, urlparse

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - optional dependency for MySQL runtime
    pymysql = None
    DictCursor = None


_PLACEHOLDER_PATTERN = re.compile(r"%\((\w+)\)s")
_MYSQL_CRYPTOGRAPHY_HINT = (
    "MySQL authentication requires the `cryptography` package because the server is using "
    "`caching_sha2_password` or `sha256_password`. Install it with `pip install cryptography` "
    "or `pip install -r requirements.txt`, or switch the MySQL user to `mysql_native_password`."
)


class Database:
    def __init__(self, database_url: str, sqlite_path: Path) -> None:
        self.database_url = (database_url or "").strip()
        self.sqlite_path = sqlite_path
        self.backend = self._detect_backend(self.database_url)
        self.mysql_config = self._parse_mysql_config(self.database_url) if self.backend == "mysql" else None
        self._mysql_database_ready = False
        if self.backend == "sqlite" and self.database_url.startswith("sqlite:///"):
            self.sqlite_path = Path(self.database_url.replace("sqlite:///", "", 1))
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    def _detect_backend(self, database_url: str) -> str:
        if not database_url or database_url.startswith("sqlite:///"):
            return "sqlite"
        if database_url.startswith("mysql://") or database_url.startswith("mysql+pymysql://"):
            return "mysql"
        raise RuntimeError(f"Unsupported database backend in URL: {database_url}")

    def _parse_mysql_config(self, database_url: str) -> dict[str, Any]:
        normalized = database_url.replace("mysql+pymysql://", "mysql://", 1)
        parsed = urlparse(normalized)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": int(parsed.port or 3306),
            "user": unquote(parsed.username or "root"),
            "password": unquote(parsed.password or ""),
            "database": unquote(parsed.path.lstrip("/") or "finavatar"),
            "charset": params.get("charset", "utf8mb4"),
        }

    @staticmethod
    def _quote_identifier(name: str) -> str:
        return "`" + str(name).replace("`", "``") + "`"

    @staticmethod
    def _reraise_mysql_connect_error(exc: Exception) -> None:
        message = str(exc)
        if "cryptography" in message and ("caching_sha2_password" in message or "sha256_password" in message):
            raise RuntimeError(_MYSQL_CRYPTOGRAPHY_HINT) from exc
        raise exc

    def _ensure_mysql_database(self) -> None:
        if self._mysql_database_ready:
            return
        if pymysql is None:
            raise RuntimeError("MySQL driver PyMySQL is not installed. Run `pip install -r requirements.txt` first.")
        config = dict(self.mysql_config or {})
        database_name = str(config.pop("database", "") or "finavatar")
        try:
            connection = pymysql.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                charset=config["charset"],
                autocommit=True,
            )
        except RuntimeError as exc:
            self._reraise_mysql_connect_error(exc)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS {self._quote_identifier(database_name)} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            connection.close()
        self._mysql_database_ready = True

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if self.backend == "sqlite":
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        if self.backend == "mysql":
            self._ensure_mysql_database()
            if pymysql is None:
                raise RuntimeError("MySQL driver PyMySQL is not installed. Run `pip install -r requirements.txt` first.")
            config = dict(self.mysql_config or {})
            try:
                conn = pymysql.connect(
                    host=config["host"],
                    port=config["port"],
                    user=config["user"],
                    password=config["password"],
                    database=config["database"],
                    charset=config["charset"],
                    cursorclass=DictCursor,
                    autocommit=False,
                )
            except RuntimeError as exc:
                self._reraise_mysql_connect_error(exc)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        raise RuntimeError("Only SQLite and MySQL backends are supported.")

    def _sql(self, statement: str) -> str:
        if self.backend == "sqlite":
            return _PLACEHOLDER_PATTERN.sub(r":\1", statement)
        return statement

    def execute(self, statement: str, params: dict[str, Any] | None = None) -> None:
        with self.connection() as conn:
            if self.backend == "sqlite":
                conn.execute(self._sql(statement), params or {})
                return
            with conn.cursor() as cursor:
                cursor.execute(self._sql(statement), params or {})

    def fetchone(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self.connection() as conn:
            if self.backend == "sqlite":
                cursor = conn.execute(self._sql(statement), params or {})
                row = cursor.fetchone()
            else:
                with conn.cursor() as cursor:
                    cursor.execute(self._sql(statement), params or {})
                    row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def fetchall(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if self.backend == "sqlite":
                cursor = conn.execute(self._sql(statement), params or {})
                rows = cursor.fetchall()
            else:
                with conn.cursor() as cursor:
                    cursor.execute(self._sql(statement), params or {})
                    rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_many(self, statement: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        with self.connection() as conn:
            sql = self._sql(statement)
            if self.backend == "sqlite":
                conn.executemany(sql, items)
                return
            with conn.cursor() as cursor:
                cursor.executemany(sql, items)

    def scalar(self, statement: str, params: dict[str, Any] | None = None, default: Any = None) -> Any:
        row = self.fetchone(statement, params)
        if not row:
            return default
        return next(iter(row.values()), default)

    def upsert(
        self,
        table: str,
        payload: dict[str, Any],
        *,
        conflict_keys: list[str],
        update_keys: list[str] | None = None,
    ) -> None:
        columns = list(payload.keys())
        update_columns = list(update_keys or [column for column in columns if column not in conflict_keys])
        column_sql = ", ".join(columns)
        value_sql = ", ".join(f"%({column})s" for column in columns)
        if self.backend == "mysql":
            if update_columns:
                update_sql = ", ".join(f"{column} = VALUES({column})" for column in update_columns)
                statement = f"INSERT INTO {table} ({column_sql}) VALUES ({value_sql}) ON DUPLICATE KEY UPDATE {update_sql}"
            else:
                statement = f"INSERT IGNORE INTO {table} ({column_sql}) VALUES ({value_sql})"
        else:
            conflict_sql = ", ".join(conflict_keys)
            if update_columns:
                update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
                statement = (
                    f"INSERT INTO {table} ({column_sql}) VALUES ({value_sql}) "
                    f"ON CONFLICT({conflict_sql}) DO UPDATE SET {update_sql}"
                )
            else:
                statement = f"INSERT INTO {table} ({column_sql}) VALUES ({value_sql}) ON CONFLICT({conflict_sql}) DO NOTHING"
        self.execute(statement, payload)

    def column_names(self, table: str) -> set[str]:
        if self.backend == "sqlite":
            with self.connection() as conn:
                rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return {str(row["name"]) for row in rows}
        if self.backend == "mysql":
            rows = self.fetchall(
                """
                SELECT COLUMN_NAME AS name
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %(schema)s AND TABLE_NAME = %(table)s
                """,
                {"schema": (self.mysql_config or {}).get("database"), "table": table},
            )
            return {str(row["name"]) for row in rows}
        return set()

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        if column in self.column_names(table):
            return
        self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ignore_duplicate_index_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "already exists" in message or "duplicate key name" in message or "1061" in message

    def _ensure_index(self, name: str, table: str, columns: str) -> None:
        try:
            self.execute(f"CREATE INDEX {name} ON {table}({columns})")
        except Exception as exc:
            if self._ignore_duplicate_index_error(exc):
                return
            raise

    def _bootstrap_sqlite_app_data(self) -> None:
        if self.backend != "mysql" or not self.sqlite_path.exists():
            return
        legacy = sqlite3.connect(self.sqlite_path)
        legacy.row_factory = sqlite3.Row
        table_order = [
            "users",
            "user_sessions",
            "user_profiles",
            "documents",
            "document_sections",
            "document_chunks",
            "document_pages",
            "conversations",
            "conversation_messages",
            "agent_memories",
            "avatar_profiles",
        ]
        try:
            for table in table_order:
                if int(self.scalar(f"SELECT COUNT(*) AS count FROM {table}", default=0) or 0) > 0:
                    continue
                try:
                    rows = [dict(row) for row in legacy.execute(f"SELECT * FROM {table}").fetchall()]
                except sqlite3.OperationalError:
                    continue
                if not rows:
                    continue
                columns = list(rows[0].keys())
                statement = (
                    f"INSERT INTO {table} ({', '.join(columns)}) "
                    f"VALUES ({', '.join(f'%({column})s' for column in columns)})"
                )
                self.execute_many(statement, rows)
        finally:
            legacy.close()

    def init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(64) PRIMARY KEY,
                username VARCHAR(80) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                last_login_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                token VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                expires_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                profile_id VARCHAR(64) PRIMARY KEY,
                risk_level VARCHAR(40) NOT NULL,
                investment_horizon VARCHAR(40) NOT NULL,
                markets_json LONGTEXT NOT NULL,
                sector_preferences_json LONGTEXT NOT NULL,
                style_preference VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                stored_path VARCHAR(512) NOT NULL,
                category VARCHAR(64) NOT NULL,
                title VARCHAR(255) NOT NULL,
                suffix VARCHAR(20) NOT NULL,
                uploaded_at VARCHAR(40) NOT NULL,
                chunk_count INTEGER NOT NULL,
                section_count INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                summary TEXT NOT NULL,
                headings_json LONGTEXT NOT NULL,
                keywords_json LONGTEXT NOT NULL,
                embedding_json LONGTEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_sections (
                section_id VARCHAR(64) PRIMARY KEY,
                doc_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(255) NOT NULL,
                order_index INTEGER NOT NULL,
                summary TEXT NOT NULL,
                preview TEXT NOT NULL,
                embedding_json LONGTEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                chunk_id VARCHAR(64) PRIMARY KEY,
                doc_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                section_id VARCHAR(64) NOT NULL,
                section_title VARCHAR(255) NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_title VARCHAR(255) NOT NULL,
                chunk_kind VARCHAR(40) NOT NULL,
                text LONGTEXT NOT NULL,
                preview TEXT NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                page_start INTEGER NULL,
                page_end INTEGER NULL,
                word_count INTEGER NOT NULL,
                embedding_json LONGTEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_pages (
                doc_id VARCHAR(64) NOT NULL,
                page_number INTEGER NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                preview TEXT NOT NULL,
                text LONGTEXT NOT NULL,
                PRIMARY KEY (doc_id, page_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(255) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id VARCHAR(64) PRIMARY KEY,
                conversation_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                role VARCHAR(20) NOT NULL,
                content LONGTEXT NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                task_type VARCHAR(80) NULL,
                route_json LONGTEXT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_memories (
                user_id VARCHAR(64) PRIMARY KEY,
                summary TEXT NOT NULL,
                recent_symbols_json LONGTEXT NOT NULL,
                recent_sectors_json LONGTEXT NOT NULL,
                preference_tags_json LONGTEXT NOT NULL,
                recent_tasks_json LONGTEXT NOT NULL,
                recent_actions_json LONGTEXT NOT NULL,
                updated_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS avatar_profiles (
                user_id VARCHAR(64) PRIMARY KEY,
                payload_json LONGTEXT NOT NULL,
                updated_at VARCHAR(40) NOT NULL
            )
            """,
        ]
        for statement in statements:
            self.execute(statement)
        self._ensure_index("idx_user_sessions_user", "user_sessions", "user_id")
        self._ensure_index("idx_documents_user", "documents", "user_id")
        self._ensure_index("idx_sections_doc", "document_sections", "doc_id")
        self._ensure_index("idx_sections_user", "document_sections", "user_id")
        self._ensure_index("idx_chunks_doc", "document_chunks", "doc_id")
        self._ensure_index("idx_chunks_user", "document_chunks", "user_id")
        self._ensure_index("idx_chunks_section", "document_chunks", "section_id")
        self._ensure_index("idx_pages_doc", "document_pages", "doc_id")
        self._ensure_index("idx_conversations_user", "conversations", "user_id")
        self._ensure_index("idx_conversation_messages_conversation", "conversation_messages", "conversation_id")
        self._ensure_index("idx_conversation_messages_user", "conversation_messages", "user_id")
        self._bootstrap_sqlite_app_data()
