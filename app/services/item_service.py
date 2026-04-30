from app.storage.sqlite_repo import ItemRecord, SqliteRepo


class ItemService:
    def __init__(self, repo: SqliteRepo) -> None:
        self.repo = repo

    def get(self, key: str) -> ItemRecord | None:
        return self.repo.get_item_by_key(key)

    def upsert(self, key: str, value: str, expected_version: int | None) -> ItemRecord:
        return self.repo.upsert_item(key=key, value=value, expected_version=expected_version)

    def list_since(self, since: str | None, limit: int) -> list[ItemRecord]:
        return self.repo.list_items_since(since=since, limit=limit)
