from pydantic import BaseModel


class FileMetaResponse(BaseModel):
    key: str
    original_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    version: int
    created_at: str
    updated_at: str
    is_deleted: bool
    deleted_at: str | None


class FileListResponse(BaseModel):
    files: list[FileMetaResponse]
    next_since: str | None


class FileGcResponse(BaseModel):
    scanned: int
    deleted_records: int
    deleted_blobs: int


class FileDeleteResponse(BaseModel):
    key: str
    hard_deleted: bool
