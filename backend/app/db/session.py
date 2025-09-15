from __future__ import annotations

import logging
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine():
    settings = get_settings()
    url = settings.sqlalchemy_database_url

    # Optimized connection pool settings for remote database
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        # Connection pool optimization for remote DB
        pool_size=20,  # Increased from default 5
        max_overflow=30,  # Allow burst connections
        pool_recycle=3600,  # Recycle connections every hour
        pool_timeout=30,  # Wait up to 30s for connection
        # Performance optimizations
        echo=False,  # Disable SQL logging in production
        connect_args={
            "connect_timeout": 10,  # 10s connection timeout
            "application_name": "chatai_backend",
            "options": "-c jit=off",  # Disable JIT for faster simple queries
        },
    )


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
    """
    Create a new database session.

    Use this when you need a session outside of FastAPI dependency injection.
    Remember to close the session when done.
    """
    return _session_factory()()


def get_engine():
    """Get the SQLAlchemy engine instance."""
    return _engine()


@contextmanager
def db_session() -> Iterator[Session]:
    """
    Context manager for database sessions with guaranteed cleanup.

    This is the RECOMMENDED way to handle database sessions.
    Ensures proper resource cleanup even if exceptions occur.

    Usage:
        with db_session() as session:
            # Do database work
            user = session.query(User).first()
            session.commit()
        # Session is automatically closed here
    """
    session = _session_factory()()
    try:
        yield session
    except Exception as e:
        logger.warning("Database session error, rolling back: %s", e)
        session.rollback()
        raise
    finally:
        try:
            session.close()
        except Exception as e:
            logger.error("Failed to close database session: %s", e)


@contextmanager
def db_transaction() -> Iterator[Session]:
    """
    Context manager for database transactions with automatic commit/rollback.

    Automatically commits on success, rolls back on exception.

    Usage:
        with db_transaction() as session:
            user = User(name="John")
            session.add(user)
            # Automatically commits here if no exception
        # Session is automatically closed
    """
    session = _session_factory()()
    try:
        yield session
        session.commit()
        logger.debug("Database transaction committed successfully")
    except Exception as e:
        logger.warning("Database transaction failed, rolling back: %s", e)
        session.rollback()
        raise
    finally:
        try:
            session.close()
        except Exception as e:
            logger.error("Failed to close database session: %s", e)
