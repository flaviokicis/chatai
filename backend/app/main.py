from __future__ import annotations

import logging
import os

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
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

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Modern FastAPI lifespan event handler for startup/shutdown."""
    # Startup
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
        except Exception as e:
            logger.warning("Redis connection failed (%s), falling back to in-memory store", e)
            ctx.store = InMemoryStore()
    else:
        ctx.store = InMemoryStore()
        logger.info("Conversation store initialized with in-memory backend")

    # Initialize rate limiter
    try:
        if redis_url:
            ctx.rate_limiter = RateLimiter(RedisRateLimiterBackend(redis_url))
            logger.info("Rate limiter initialized with Redis backend")
        else:
            ctx.rate_limiter = RateLimiter(InMemoryRateLimiterBackend())
            logger.info("Rate limiter initialized with in-memory backend")
    except Exception as e:
        logger.warning("Rate limiter initialization failed: %s", e)
        ctx.rate_limiter = None

    # Configure default session policy (stable); channels may override
    ctx.session_policy = StableSessionPolicy()

    # Initialize database tables
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured (create_all)")
    except Exception as e:
        logger.warning("Failed to create DB tables on startup: %s", e)

    yield
    
    # Shutdown (if needed)
    logger.info("Application shutting down")

app = FastAPI(
    title="ChatAI Backend API", 
    version="0.3.0",
    description="Modern ChatAI backend with admin panel and GDPR compliance",
    lifespan=lifespan
)

# Enable CORS for the Next.js frontend (localhost dev defaults)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",  # Allow backend to call itself
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

# Add session middleware for admin authentication
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET_KEY", "your-secret-key-change-in-production"),
    max_age=86400,  # 24 hours
)
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


# Modern FastAPI startup moved to lifespan context manager


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


# Aggregate API router mounted
app.include_router(api_router)

# Add legacy webhook routes for backward compatibility (without /api prefix)
from app.whatsapp.router import router as whatsapp_router
app.include_router(whatsapp_router)

# Serve Next.js frontend with SPA-style routing (PRODUCTION ONLY)
# In development, frontend runs separately on port 3000
# Override with SERVE_FRONTEND=true for local production testing
serve_frontend = (
    os.getenv("NODE_ENV") == "production" or 
    os.getenv("SERVE_FRONTEND", "").lower() == "true"
)

if serve_frontend:
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.exists(static_dir):
        # Serve Next.js static assets (JS, CSS, images)
        static_assets_dir = os.path.join(static_dir, "static")
        if os.path.exists(static_assets_dir):
            app.mount("/_next/static", StaticFiles(directory=static_assets_dir), name="nextjs_assets")
            logger.info("Next.js static assets mounted from %s", static_assets_dir)
        
        # Custom SPA handler for client-side routing
        from fastapi import Request
        from fastapi.responses import FileResponse
        
        server_app_dir = os.path.join(static_dir, "server", "app")
        
        @app.get("/{full_path:path}")
        async def spa_handler(request: Request, full_path: str):
            """Handle SPA routing - serve appropriate HTML file or fallback to index."""
            
            # CRITICAL: Skip ALL API routes to prevent conflicts
            if (full_path.startswith("api/") or 
                full_path.startswith("webhooks/") or
                full_path.startswith("health")):
                raise HTTPException(status_code=404, detail="Not Found")
            
            # Try to find the specific HTML file for this route
            html_file_path = os.path.join(server_app_dir, f"{full_path}.html")
            if os.path.exists(html_file_path):
                return FileResponse(html_file_path, media_type="text/html")
            
            # For dynamic routes or missing pages, try index.html as fallback
            index_path = os.path.join(server_app_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path, media_type="text/html")
            
            # Final fallback
            raise HTTPException(status_code=404, detail="Page not found")
        
        mode = "PRODUCTION" if os.getenv("NODE_ENV") == "production" else "DEBUG"
        logger.info("%s: SPA routing configured for frontend from %s", mode, server_app_dir)
    else:
        logger.warning("Static files directory not found: %s", static_dir)
else:
    logger.info("DEVELOPMENT: Frontend static serving disabled - run 'pnpm dev' separately")
    logger.info("To test production-like serving locally: SERVE_FRONTEND=true make dev")
