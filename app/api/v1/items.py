from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.container import get_item_service
from app.core.security import require_bearer_token
from app.schemas.item import ItemListResponse, ItemResponse, ItemUpsertRequest
from app.services.item_service import ItemService
from app.storage.sqlite_repo import VersionConflictError

router = APIRouter(prefix="/v1", tags=["items"])


def _normalize_since(since: datetime | None) -> str | None:
    if since is None:
        return None
    return since.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _to_item_response(record) -> ItemResponse:
    return ItemResponse(
        key=record.key,
        value=record.value,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "/items/{key}",
    response_model=ItemResponse,
    dependencies=[Depends(require_bearer_token)],
)
def upsert_item(
    key: str,
    payload: ItemUpsertRequest,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    if not key.strip() or len(key) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid key",
        )
    try:
        item = service.upsert(
            key=key,
            value=payload.value,
            expected_version=payload.expected_version,
        )
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Version conflict",
                "current_version": exc.current_version,
            },
        ) from exc
    return _to_item_response(item)


@router.get(
    "/items/{key}",
    response_model=ItemResponse,
    dependencies=[Depends(require_bearer_token)],
)
def get_item(
    key: str,
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    item = service.get(key)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return _to_item_response(item)


@router.get(
    "/items",
    response_model=ItemListResponse,
    dependencies=[Depends(require_bearer_token)],
)
def list_items(
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: ItemService = Depends(get_item_service),
) -> ItemListResponse:
    normalized_since = _normalize_since(since)
    items = service.list_since(since=normalized_since, limit=limit)
    item_models = [_to_item_response(item) for item in items]
    next_since = item_models[-1].updated_at if item_models else normalized_since
    return ItemListResponse(items=item_models, next_since=next_since)
