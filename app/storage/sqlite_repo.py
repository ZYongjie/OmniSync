import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ItemRecord:
    key: str
    value: str
    version: int
    created_at: str
    updated_at: str


class VersionConflictError(Exception):
    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__("Version conflict")


class SqliteRepo:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_key TEXT NOT NULL UNIQUE,
                    item_value TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_key ON items(item_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_updated_at ON items(updated_at)"
            )
            conn.commit()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ItemRecord:
        return ItemRecord(
            key=row["item_key"],
            value=row["item_value"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_item_by_key(self, key: str) -> ItemRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT item_key, item_value, version, created_at, updated_at
                FROM items
                WHERE item_key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def upsert_item(
        self, key: str, value: str, expected_version: int | None = None
    ) -> ItemRecord:
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT item_key, item_value, version, created_at, updated_at
                FROM items
                WHERE item_key = ?
                """,
                (key,),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO items(item_key, item_value, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, value, 1, now, now),
                )
            else:
                if expected_version is not None and existing["version"] != expected_version:
                    conn.rollback()
                    raise VersionConflictError(current_version=existing["version"])
                conn.execute(
                    """
                    UPDATE items
                    SET item_value = ?, version = version + 1, updated_at = ?
                    WHERE item_key = ?
                    """,
                    (value, now, key),
                )

            row = conn.execute(
                """
                SELECT item_key, item_value, version, created_at, updated_at
                FROM items
                WHERE item_key = ?
                """,
                (key,),
            ).fetchone()
            conn.commit()

        if row is None:
            raise RuntimeError("Upsert failed to return row")
        return self._row_to_item(row)

    def list_items_since(self, since: str | None, limit: int) -> list[ItemRecord]:
        query = """
            SELECT item_key, item_value, version, created_at, updated_at
            FROM items
            {where_clause}
            ORDER BY updated_at ASC, item_key ASC
            LIMIT ?
        """
        params: tuple[object, ...]
        if since:
            where_clause = "WHERE updated_at > ?"
            params = (since, limit)
        else:
            where_clause = ""
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(query.format(where_clause=where_clause), params).fetchall()
        return [self._row_to_item(row) for row in rows]
