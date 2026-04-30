from pydantic import BaseModel, Field


class ItemUpsertRequest(BaseModel):
    value: str = Field(min_length=1, max_length=100_000)
    expected_version: int | None = Field(default=None, ge=1)


class ItemResponse(BaseModel):
    key: str
    value: str
    version: int
    created_at: str
    updated_at: str


class ItemValueResponse(BaseModel):
    value: str


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    next_since: str | None
