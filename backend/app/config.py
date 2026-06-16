from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise Contract Compliance API"
    frontend_origins: str = (
        "https://nex-hack-2026.vercel.app,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500,"
        "http://127.0.0.1:8000"
    )
    max_upload_mb: int = 15
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()