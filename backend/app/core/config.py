from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env.local", extra="ignore")

    database_url: str

    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""

    session_secret: str = ""
    token_encryption_key: str = ""
    cron_secret: str = ""

    app_url: str = "http://localhost:3000"

    @property
    def sqlalchemy_url(self) -> str:
        """Neon hands out `postgresql://`, which SQLAlchemy maps to psycopg2. Naming the
        driver explicitly keeps the dashboard string copy-pasteable."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
