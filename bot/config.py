from __future__ import annotations
from pydantic import field_validator 
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    bot_token: str
    admin_ids: list[int] = []
    admin_group_id: int = 0
    admin_topic_id: int = 1

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    # Remnawave
    remnawave_api_url: str
    remnawave_api_token: str

    # DB
    database_url: str

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Misc
    log_level: str = "INFO"


settings = Settings()  # type: ignore