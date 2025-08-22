from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

try:
    # Optional dev config; ignore if missing
    from app import dev_config as _dev  # type: ignore
except Exception:  # pragma: no cover - optional
    _dev = None  # type: ignore[assignment]


class Settings(BaseSettings):
    twilio_auth_token: str = Field(default="test", alias="TWILIO_AUTH_TOKEN")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    google_api_key: str = Field(default="test", alias="GOOGLE_API_KEY")
    openai_api_key: str = Field(default="test", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")
    llm_provider: str = Field(default="google_genai", alias="LLM_PROVIDER")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    # Optional components to compose a URL when REDIS_URL is not provided
    redis_host: str | None = Field(default=None, alias="REDIS_HOST")
    redis_port: int | None = Field(default=None, alias="REDIS_PORT")
    redis_db: int | None = Field(default=None, alias="REDIS_DB")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")
    # Database
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    # Optional debug flag via environment (DEBUG=true) in addition to dev_config.py
    debug: bool = Field(default=False, alias="DEBUG")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def redis_conn_url(self) -> str | None:
        """Return a Redis connection URL.
        Prefers `REDIS_URL`; otherwise constructs from host/port/db/password.
        """
        if self.redis_url:
            return self.redis_url
        if not self.redis_host:
            return None
        host = self.redis_host
        port = self.redis_port or 6379
        db = self.redis_db or 0
        password = (self.redis_password or "").strip()
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/{db}"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return SQLAlchemy-compatible database URL, with a sensible default for local dev.

        Default: postgresql+psycopg://postgres:postgres@localhost:5432/chatai
        """
        if self.database_url and self.database_url.strip():
            return self.database_url
        return "postgresql+psycopg://postgres:postgres@localhost:5432/chatai"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def is_debug_enabled() -> bool:
    """Return True if debug logging is enabled.

    Priority:
    1) app.dev_config.debug (if present)
    2) Settings().debug (env var DEBUG)
    """
    if _dev is not None:
        val = getattr(_dev, "debug", None)
        if isinstance(val, bool):
            return val
    try:
        return bool(get_settings().debug)
    except Exception:
        return False
