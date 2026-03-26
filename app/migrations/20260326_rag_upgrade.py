from __future__ import annotations

from app.config import get_settings
from app.storage.database import Database


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_url, settings.app_db_path)
    db.init_schema()
    print("RAG schema upgrade completed.")


if __name__ == "__main__":
    main()
