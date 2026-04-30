from functools import lru_cache

from app.core.config import get_settings
from app.services.item_service import ItemService
from app.storage.sqlite_repo import SqliteRepo


@lru_cache
def get_repo() -> SqliteRepo:
    settings = get_settings()
    return SqliteRepo(db_path=settings.db_path)


@lru_cache
def get_item_service() -> ItemService:
    return ItemService(repo=get_repo())
