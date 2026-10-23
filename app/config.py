from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr
    cors_origins: list[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    demo_api_token: SecretStr = SecretStr("")
    demo_customer_id: int = Field(default=2, gt=0)
