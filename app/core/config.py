from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_token: str
    db_path: str = "./data/omnisync.db"
    file_storage_path: str = "./data/files"
    file_max_bytes: int = 52428800
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
