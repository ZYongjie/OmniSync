import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import UploadFile

from app.storage.sqlite_repo import FileRecord, SqliteRepo


class FileTooLargeError(Exception):
    pass


class EmptyFileError(Exception):
    pass


@dataclass
class GcResult:
    scanned: int
    deleted_records: int
    deleted_blobs: int


class FileService:
    def __init__(self, repo: SqliteRepo, storage_path: str, max_bytes: int) -> None:
        self.repo = repo
        self.storage_root = Path(storage_path)
        self.max_bytes = max_bytes
        self.storage_root.mkdir(parents=True, exist_ok=True)

    async def upload(
        self, key: str, upload_file: UploadFile, expected_version: int | None
    ) -> FileRecord:
        temp_dir = self.storage_root / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        tmp_name = f"upload-{os.getpid()}-{key.replace('/', '_')}"
        tmp_path = temp_dir / tmp_name

        hasher = hashlib.sha256()
        size = 0
        try:
            with tmp_path.open("wb") as temp_fp:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise FileTooLargeError(
                            f"File exceeds max size of {self.max_bytes} bytes"
                        )
                    hasher.update(chunk)
                    temp_fp.write(chunk)

            if size == 0:
                raise EmptyFileError("Empty file is not allowed")

            checksum = hasher.hexdigest()
            relative_path = Path(checksum[:2]) / f"{checksum}.bin"
            final_path = self.storage_root / relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)

            if final_path.exists():
                tmp_path.unlink(missing_ok=True)
            else:
                tmp_path.replace(final_path)

            return self.repo.upsert_file(
                key=key,
                original_name=upload_file.filename or key,
                content_type=upload_file.content_type or "application/octet-stream",
                size_bytes=size,
                checksum_sha256=checksum,
                storage_path=relative_path.as_posix(),
                expected_version=expected_version,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            await upload_file.close()

    def get_meta(self, key: str) -> FileRecord | None:
        return self.repo.get_file_by_key(key)

    def soft_delete(self, key: str, expected_version: int | None) -> FileRecord | None:
        return self.repo.soft_delete_file(key=key, expected_version=expected_version)

    def hard_delete(self, key: str, expected_version: int | None) -> FileRecord | None:
        record = self.repo.hard_delete_file(key=key, expected_version=expected_version)
        if record is None:
            return None

        # Keep deduplicated blob only when still referenced by active file records.
        if not self.repo.is_storage_path_referenced_by_active(record.storage_path):
            blob_path = self.resolve_disk_path(record.storage_path)
            blob_path.unlink(missing_ok=True)

        return record

    def list_since(self, since: str | None, limit: int) -> list[FileRecord]:
        return self.repo.list_files_since(since=since, limit=limit)

    def resolve_disk_path(self, storage_path: str) -> Path:
        return self.storage_root / storage_path

    def collect_garbage(self, grace_seconds: int, limit: int) -> GcResult:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=grace_seconds)
        cutoff_iso = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        candidates = self.repo.list_deleted_files_before(before=cutoff_iso, limit=limit)

        deleted_records = 0
        deleted_blobs = 0
        for record in candidates:
            if not self.repo.is_storage_path_referenced_by_active(record.storage_path):
                blob_path = self.resolve_disk_path(record.storage_path)
                if blob_path.exists():
                    blob_path.unlink(missing_ok=True)
                    deleted_blobs += 1

            if self.repo.purge_deleted_file(record.key):
                deleted_records += 1

        return GcResult(
            scanned=len(candidates),
            deleted_records=deleted_records,
            deleted_blobs=deleted_blobs,
        )
