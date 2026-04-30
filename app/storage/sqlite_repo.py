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


@dataclass
class FileRecord:
    key: str
    original_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    storage_path: str
    version: int
    created_at: str
    updated_at: str
    deleted_at: str | None


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_key TEXT NOT NULL UNIQUE,
                    original_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_files_key ON files(file_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_updated_at ON files(updated_at)"
            )
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(files)").fetchall()
            }
            if "deleted_at" not in existing_columns:
                conn.execute("ALTER TABLE files ADD COLUMN deleted_at TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_deleted_at ON files(deleted_at)"
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

    @staticmethod
    def _row_to_file(row: sqlite3.Row) -> FileRecord:
        return FileRecord(
            key=row["file_key"],
            original_name=row["original_name"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            checksum_sha256=row["checksum_sha256"],
            storage_path=row["storage_path"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

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

    def get_file_by_key(self, key: str, include_deleted: bool = False) -> FileRecord | None:
        where_clause = "WHERE file_key = ?"
        if not include_deleted:
            where_clause += " AND deleted_at IS NULL"
        with self._connect() as conn:
            row = conn.execute(
                """ 
                SELECT file_key, original_name, content_type, size_bytes,
                       checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
                FROM files
                {where_clause}
                """.format(where_clause=where_clause),
                (key,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_file(row)

    def upsert_file(
        self,
        key: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        storage_path: str,
        expected_version: int | None = None,
    ) -> FileRecord:
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT file_key, version
                FROM files
                WHERE file_key = ?
                """,
                (key,),
            ).fetchone()

            if existing is None:
                conn.execute(
                    """
                    INSERT INTO files(
                        file_key, original_name, content_type, size_bytes,
                        checksum_sha256, storage_path, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        original_name,
                        content_type,
                        size_bytes,
                        checksum_sha256,
                        storage_path,
                        1,
                        now,
                        now,
                    ),
                )
            else:
                if expected_version is not None and existing["version"] != expected_version:
                    conn.rollback()
                    raise VersionConflictError(current_version=existing["version"])
                conn.execute(
                    """
                    UPDATE files
                    SET original_name = ?,
                        content_type = ?,
                        size_bytes = ?,
                        checksum_sha256 = ?,
                        storage_path = ?,
                        deleted_at = NULL,
                        version = version + 1,
                        updated_at = ?
                    WHERE file_key = ?
                    """,
                    (
                        original_name,
                        content_type,
                        size_bytes,
                        checksum_sha256,
                        storage_path,
                        now,
                        key,
                    ),
                )

            row = conn.execute(
                """
                SELECT file_key, original_name, content_type, size_bytes,
                      checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
                FROM files
                WHERE file_key = ?
                """,
                (key,),
            ).fetchone()
            conn.commit()

        if row is None:
            raise RuntimeError("Upsert file failed to return row")
        return self._row_to_file(row)

    def list_files_since(self, since: str | None, limit: int) -> list[FileRecord]:
        query = """
            SELECT file_key, original_name, content_type, size_bytes,
                   checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
            FROM files
            {where_clause}
            ORDER BY updated_at ASC, file_key ASC
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
        return [self._row_to_file(row) for row in rows]

    def soft_delete_file(
        self, key: str, expected_version: int | None = None
    ) -> FileRecord | None:
        now = self._utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT file_key, original_name, content_type, size_bytes,
                       checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
                FROM files
                WHERE file_key = ?
                """,
                (key,),
            ).fetchone()
            if existing is None:
                conn.rollback()
                return None

            if expected_version is not None and existing["version"] != expected_version:
                conn.rollback()
                raise VersionConflictError(current_version=existing["version"])

            conn.execute(
                """
                UPDATE files
                SET deleted_at = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE file_key = ?
                """,
                (now, now, key),
            )
            row = conn.execute(
                """
                SELECT file_key, original_name, content_type, size_bytes,
                       checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
                FROM files
                WHERE file_key = ?
                """,
                (key,),
            ).fetchone()
            conn.commit()

        if row is None:
            return None
        return self._row_to_file(row)

    def list_deleted_files_before(self, before: str, limit: int) -> list[FileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT file_key, original_name, content_type, size_bytes,
                       checksum_sha256, storage_path, version, created_at, updated_at, deleted_at
                FROM files
                WHERE deleted_at IS NOT NULL AND updated_at <= ?
                ORDER BY updated_at ASC, file_key ASC
                LIMIT ?
                """,
                (before, limit),
            ).fetchall()
        return [self._row_to_file(row) for row in rows]

    def is_storage_path_referenced_by_active(self, storage_path: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM files
                WHERE storage_path = ? AND deleted_at IS NULL
                LIMIT 1
                """,
                (storage_path,),
            ).fetchone()
        return row is not None

    def purge_deleted_file(self, key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM files WHERE file_key = ? AND deleted_at IS NOT NULL",
                (key,),
            )
            conn.commit()
        return cursor.rowcount > 0
