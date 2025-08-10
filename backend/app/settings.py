from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    twilio_auth_token: str = Field(..., alias="TWILIO_AUTH_TOKEN")
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    google_api_key: str = Field(..., alias="GOOGLE_API_KEY")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    # Optional components to compose a URL when REDIS_URL is not provided
    redis_host: str | None = Field(default=None, alias="REDIS_HOST")
    redis_port: int | None = Field(default=None, alias="REDIS_PORT")
    redis_db: int | None = Field(default=None, alias="REDIS_DB")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
