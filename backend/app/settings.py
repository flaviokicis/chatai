from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# REMOVED: dev_config.py support - Use DEVELOPMENT_MODE environment variable instead


class Settings(BaseSettings):
    twilio_auth_token: str = Field(default="test", alias="TWILIO_AUTH_TOKEN")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    # WhatsApp Cloud API
    whatsapp_verify_token: str = Field(default="test", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_access_token: str = Field(default="test", alias="WHATSAPP_ACCESS_TOKEN")
    # WhatsApp provider: "twilio" (default) or "cloud_api"
    whatsapp_provider: str = Field(default="cloud_api", alias="WHATSAPP_PROVIDER")
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
    # Vector database URL for pgvector
    pg_vector_database_url: str | None = Field(default=None, alias="PG_VECTOR_DATABASE_URL")
    # Legacy debug flag - DEPRECATED: Use DEVELOPMENT_MODE instead
    debug: bool = Field(default=False, alias="DEBUG")
    # Development mode flag - THE UNIFIED FLAG for all development features
    development_mode: bool = Field(default=False, alias="DEVELOPMENT_MODE")
    # Admin authentication
    admin_username: str = Field(default="super@inboxed.com", alias="ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")
    # Audio validation
    max_audio_duration_seconds: int = Field(
        default=300, alias="MAX_AUDIO_DURATION_SECONDS"
    )  # 5 minutes

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

    @property
    def vector_database_url(self) -> str:
        """Return pgvector database URL, falling back to main database if not specified.
        
        Prefers PG_VECTOR_DATABASE_URL, falls back to DATABASE_URL, then default.
        """
        if self.pg_vector_database_url and self.pg_vector_database_url.strip():
            return self.pg_vector_database_url
        return self.sqlalchemy_database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def is_debug_enabled() -> bool:
    """
    DEPRECATED: Use is_development_mode() instead.

    This function is kept for backward compatibility only.
    """
    return is_development_mode()


def is_development_mode() -> bool:
    """
    Unified function to check if we're in development mode.

    This should be used throughout the codebase for ANY development-only features.

    Returns True ONLY if DEVELOPMENT_MODE=true environment variable is set.

    This is the single source of truth for development vs production mode.
    """
    try:
        settings = get_settings()
        return bool(settings.development_mode)
    except Exception:
        return False
