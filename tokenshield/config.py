from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    upstream_base_url: str = "https://api.openai.com"
    upstream_api_key: str | None = None
    database_url: str = "sqlite:///./tokenshield.db"
    compression_enabled: bool = True
    compression_min_chars: int = 800
    raw_retention_hours: int = 24
    max_body_bytes: int = 20_000_000
    pricing_json: str = "{}"
    model_config = SettingsConfigDict(env_prefix="TOKENSHIELD_", env_file=".env")


settings = Settings()
