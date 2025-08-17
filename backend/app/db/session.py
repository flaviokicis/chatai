from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import get_settings


@lru_cache(maxsize=1)
def _engine():
    settings = get_settings()
    url = settings.sqlalchemy_database_url
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), autoflush=False, autocommit=False, future=True)


def get_db_session() -> Generator[Session, None, None]:
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_session() -> Session:
    """Create a SQLAlchemy session outside FastAPI dependency injection.

    Useful for background tasks and framework code paths where DI is not available.
    """
    return _session_factory()()


def get_engine():
    """Expose the shared engine for metadata operations (e.g., create_all)."""
    return _engine()
