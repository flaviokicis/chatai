from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from langchain.chat_models import init_chat_model

from app.config.loader import load_json_config
from app.core.app_context import AppContext, get_app_context, set_app_context
from app.core.langchain_adapter import LangChainToolsLLM
from app.core.session import StableSessionPolicy
from app.core.state import InMemoryStore, RedisStore
from app.router import api_router
from app.settings import get_settings

app = FastAPI(title="Chatai Twilio Webhook", version="0.2.0")
logger = logging.getLogger("uvicorn.error")
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
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key
    # Default bootstrap LLM; per-agent overrides supported via config
    chat = init_chat_model(settings.llm_model, model_provider="google_genai")
    ctx = get_app_context(app)
    ctx.llm = LangChainToolsLLM(chat)
    ctx.llm_model = settings.llm_model
    logger.info("Default LLM initialized: model=%s provider=%s", settings.llm_model, "google_genai")
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


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


# Aggregate API router mounted
app.include_router(api_router)
