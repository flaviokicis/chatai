from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langchain.chat_models import init_chat_model

from app.config.loader import load_json_config
from app.core.app_context import AppContext, get_app_context, set_app_context
from app.core.logging import RequestIdMiddleware, setup_logging
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.session import StableSessionPolicy
from app.core.state import InMemoryStore, RedisStore
from app.db.base import Base
from app.db.models import Tenant
from app.db.session import create_session, get_engine
from app.router import api_router
from app.services.rate_limiter import (
    InMemoryRateLimiterBackend,
    RateLimiter,
    RedisRateLimiterBackend,
)
from app.services.tenant_service import TenantService
from app.settings import get_settings

setup_logging()
app = FastAPI(title="Chatai Twilio Webhook", version="0.2.0")

# Enable CORS for the Next.js frontend (localhost dev defaults)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)
logger = logging.getLogger(__name__)
set_app_context(
    app,
    AppContext(
        config_provider=None,
        store=InMemoryStore(),
        llm=None,  # type: ignore[assignment] - will be set on startup
        llm_model="",
    ),
)


@app.on_event("startup")
def _init_llm() -> None:
    settings = get_settings()
    
    # Configure API keys based on provider
    if settings.llm_provider == "openai":
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    else:
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    
    # Default bootstrap LLM; per-agent overrides supported via config
    chat = init_chat_model(settings.llm_model, model_provider=settings.llm_provider)
    ctx = get_app_context(app)
    ctx.llm = LangChainToolsLLM(chat)
    ctx.llm_model = settings.llm_model
    logger.info("Default LLM initialized: model=%s provider=%s", settings.llm_model, settings.llm_provider)
    # Load multitenant config from JSON if provided
    config_path = os.environ.get("CONFIG_JSON_PATH") or os.getenv("CONFIG_JSON_PATH")
    if config_path:
        ctx.config_provider = load_json_config(config_path)
        logger.info("Config provider initialized from %s", config_path)
    else:
        ctx.config_provider = load_json_config("config.json")
        logger.info("Config provider initialized from default config.json")

    # Initialize conversation store: prefer Redis when configured
    try:
        redis_url = settings.redis_conn_url
    except Exception:
        redis_url = settings.redis_url
    if redis_url:
        try:
            ctx.store = RedisStore(redis_url)
            logger.info("Conversation store initialized with Redis: %s", redis_url)
        except Exception as exc:  # pragma: no cover - startup log only
            logger.warning("Failed to initialize Redis store (%s). Falling back to memory.", exc)
            ctx.store = InMemoryStore()
    else:
        logger.info("Conversation store initialized in-memory")

    # Configure default session policy (stable); channels may override
    ctx.session_policy = StableSessionPolicy()

    # Initialize rate limiter backend based on Redis availability (re-use redis_url)
    try:
        if redis_url:
            ctx.rate_limiter = RateLimiter(RedisRateLimiterBackend(redis_url))
            logger.info("Rate limiter initialized with Redis backend")
        else:
            ctx.rate_limiter = RateLimiter(InMemoryRateLimiterBackend())
            logger.info("Rate limiter initialized in-memory")
    except Exception as exc:  # pragma: no cover - startup log only
        logger.warning("Rate limiter initialization failed (%s); disabling rate limiting", exc)
        ctx.rate_limiter = None

    # Ensure database tables exist in local/dev environments.
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured (create_all)")
        # Seed a default tenant in empty dev DBs to improve DX
        try:
            session = create_session()
            try:
                exists = session.query(Tenant).first() is not None
                if not exists:
                    TenantService(session).create_tenant(
                        first_name="Demo",
                        last_name="Tenant",
                        email="demo@example.com",
                    )
                    logger.info("Seeded default demo tenant (UUIDv7)")
            finally:
                session.close()
        except Exception:
            # Non-fatal in production/CI
            pass
    except Exception as exc:  # pragma: no cover - startup log only
        logger.warning("Failed to create DB tables on startup: %s", exc)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


# Aggregate API router mounted
app.include_router(api_router)
