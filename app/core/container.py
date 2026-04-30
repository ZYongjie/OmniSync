from functools import lru_cache

from app.core.config import get_settings
from app.services.file_service import FileService
from app.services.item_service import ItemService
from app.storage.sqlite_repo import SqliteRepo


@lru_cache
def get_repo() -> SqliteRepo:
    settings = get_settings()
    return SqliteRepo(db_path=settings.db_path)


@lru_cache
def get_item_service() -> ItemService:
    return ItemService(repo=get_repo())


@lru_cache
def get_file_service() -> FileService:
    settings = get_settings()
    return FileService(
        repo=get_repo(),
        storage_path=settings.file_storage_path,
        max_bytes=settings.file_max_bytes,
    )
