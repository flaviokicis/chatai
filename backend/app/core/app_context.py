from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.config.provider import ConfigProvider
    from app.core.llm import LLMClient
    from app.core.session import SessionPolicy
    from app.core.state import ConversationStore
    from app.services.rate_limiter import RateLimiter
    from app.services.processing_cancellation_manager import ProcessingCancellationManager


@dataclass(slots=True)
class AppContext:
    config_provider: ConfigProvider | None
    store: ConversationStore
    llm: LLMClient | None
    llm_model: str
    session_policy: SessionPolicy | None = None
    rate_limiter: RateLimiter | None = None
    cancellation_manager: ProcessingCancellationManager | None = None


def set_app_context(app: FastAPI, ctx: AppContext) -> None:
    # Store one typed context object under app.state
    app.state.ctx = ctx


def get_app_context(app: FastAPI) -> AppContext:
    # Retrieve and cast from app.state
    return cast("AppContext", app.state.ctx)
