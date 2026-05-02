from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    bot_token: str
    admin_ids: List[int] = []

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/staging_bot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI
    ai_provider: str = "replicate"
    ai_api_key: str = ""
    ai_model: str = "stability-ai/sdxl:latest"

    # Storage
    storage_provider: str = "s3"
    s3_endpoint_url: str = "https://s3.amazonaws.com"
    s3_bucket_name: str = "staging-bot-files"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "eu-central-1"

    # Payments
    payment_provider: str = "telegram"
    payment_token: str = ""

    # Prices (in kopecks / smallest unit)
    price_room: int = 49900
    price_pro_room: int = 99900
    price_flat: int = 199900
    price_realtor_pack: int = 299900

    # App
    debug: bool = False
    log_level: str = "INFO"
    free_previews_limit: int = 1
    max_active_projects: int = 3
    max_photo_size_mb: int = 10
    watermark_path: str = "app/assets/watermark.png"

    # Webhook
    webhook_host: str = ""
    webhook_path: str = "/webhook"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(i.strip()) for i in v.split(",") if i.strip()]
        return v

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_host}{self.webhook_path}"

    @property
    def max_photo_size_bytes(self) -> int:
        return self.max_photo_size_mb * 1024 * 1024


settings = Settings()
