"""
Lightweight idempotent schema migrations for the SQLite MVP.

`create_all` only creates missing tables; it never alters existing ones.
This module adds missing columns (e.g. `messages.channel`) and creates
new tables (e.g. `product_images`, `message_attachments`) on startup so
existing dev databases stay compatible.

Safe to call repeatedly. No-op when columns/tables already exist.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


_REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "messages": [
        ("channel", "VARCHAR(16) NOT NULL DEFAULT 'whatsapp'"),
        ("message_type", "VARCHAR(16) NOT NULL DEFAULT 'text'"),
    ],
    "product_images": [
        ("embedding_json", "TEXT NOT NULL DEFAULT ''"),
    ],
}


def ensure_schema(engine: Engine) -> None:
    """
    Adds any missing columns/tables required by current ORM models.
    Tables themselves are expected to be created by `Base.metadata.create_all`
    before this is called.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _REQUIRED_COLUMNS.items():
            if table not in existing_tables:
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table)}
            for col_name, col_type in columns:
                if col_name in existing_cols:
                    continue
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                    logger.info("migration_added_column table=%s column=%s", table, col_name)
                except Exception:
                    logger.exception(
                        "migration_add_column_failed table=%s column=%s",
                        table,
                        col_name,
                    )
