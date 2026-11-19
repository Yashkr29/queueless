"""Environment-driven configuration. No secrets live in code."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # Supabase Postgres connection string (SQLAlchemy URL). Falls back to local SQLite for dev/tests.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'queueless_dev.db'}"

    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12

    cors_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 600
    auth_rate_limit_per_minute: int = 20

    demo_mode: bool = True            # show demo-flagged data in analytics
    model_dir: str = str(BACKEND_DIR / "models")
    auto_create_tables: bool = False  # SQLite dev always auto-creates; Supabase uses supabase/migrations
    ml_enabled: bool = True           # set false to force the non-ML fallback
    fcm_credentials_file: str = ""    # path to Firebase service-account JSON; empty = disabled

    @field_validator("database_url")
    @classmethod
    def _normalise_url(cls, v: str) -> str:
        # Supabase gives "postgresql://..." — force the psycopg3 driver.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
