from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.core.container import get_file_service
from app.core.security import require_bearer_token
from app.schemas.file import (
    FileDeleteResponse,
    FileGcResponse,
    FileListResponse,
    FileMetaResponse,
)
from app.services.file_service import EmptyFileError, FileService, FileTooLargeError
from app.storage.sqlite_repo import VersionConflictError

router = APIRouter(prefix="/v1", tags=["files"])


def _normalize_since(since: datetime | None) -> str | None:
    if since is None:
        return None
    return since.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _to_meta_response(record) -> FileMetaResponse:
    return FileMetaResponse(
        key=record.key,
        original_name=record.original_name,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        checksum_sha256=record.checksum_sha256,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
        is_deleted=record.deleted_at is not None,
        deleted_at=record.deleted_at,
    )


@router.put(
    "/files/{key}",
    response_model=FileMetaResponse,
    dependencies=[Depends(require_bearer_token)],
)
async def upload_file(
    key: str,
    file: UploadFile = File(...),
    expected_version: int | None = Query(default=None, ge=1),
    service: FileService = Depends(get_file_service),
) -> FileMetaResponse:
    if not key.strip() or len(key) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key")

    try:
        record = await service.upload(
            key=key,
            upload_file=file,
            expected_version=expected_version,
        )
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Version conflict",
                "current_version": exc.current_version,
            },
        ) from exc
    except (EmptyFileError, FileTooLargeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_meta_response(record)


@router.get(
    "/files/{key}/meta",
    response_model=FileMetaResponse,
    dependencies=[Depends(require_bearer_token)],
)
def get_file_meta(
    key: str,
    service: FileService = Depends(get_file_service),
) -> FileMetaResponse:
    record = service.get_meta(key)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _to_meta_response(record)


@router.get(
    "/files/{key}",
    response_class=FileResponse,
    dependencies=[Depends(require_bearer_token)],
)
def download_file(
    key: str,
    service: FileService = Depends(get_file_service),
) -> FileResponse:
    record = service.get_meta(key)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    disk_path = service.resolve_disk_path(record.storage_path)
    if not disk_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content missing")

    return FileResponse(
        path=disk_path,
        media_type=record.content_type,
        filename=record.original_name,
    )


@router.delete(
    "/files/{key}",
    response_model=FileDeleteResponse,
    dependencies=[Depends(require_bearer_token)],
)
def delete_file(
    key: str,
    expected_version: int | None = Query(default=None, ge=1),
    service: FileService = Depends(get_file_service),
) -> FileDeleteResponse:
    try:
        record = service.hard_delete(key=key, expected_version=expected_version)
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Version conflict",
                "current_version": exc.current_version,
            },
        ) from exc

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileDeleteResponse(key=record.key, hard_deleted=True)


@router.post(
    "/files/gc",
    response_model=FileGcResponse,
    dependencies=[Depends(require_bearer_token)],
)
def run_file_gc(
    grace_seconds: int = Query(default=86400, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    service: FileService = Depends(get_file_service),
) -> FileGcResponse:
    result = service.collect_garbage(grace_seconds=grace_seconds, limit=limit)
    return FileGcResponse(
        scanned=result.scanned,
        deleted_records=result.deleted_records,
        deleted_blobs=result.deleted_blobs,
    )


@router.get(
    "/files",
    response_model=FileListResponse,
    dependencies=[Depends(require_bearer_token)],
)
def list_files(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: FileService = Depends(get_file_service),
) -> FileListResponse:
    normalized_since = _normalize_since(since)
    records = service.list_since(since=normalized_since, limit=limit)
    models = [_to_meta_response(record) for record in records]
    next_since = models[-1].updated_at if models else normalized_since
    return FileListResponse(files=models, next_since=next_since)
