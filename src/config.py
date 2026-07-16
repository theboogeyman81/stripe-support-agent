"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    voyage_api_key: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    admin_api_key: str = "changeme"
