"""
Robust handoff tracking service with database-first, Redis-fallback strategy.

This service ensures that human handoff requests are never lost by using:
- Tenacity for retry logic with exponential backoff
- Database-first storage for persistence
- Redis fallback with 180-day expiration for reliability
- Comprehensive error handling and logging
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from uuid_v7.base import uuid7

from app.core.redis_keys import redis_keys
from app.db.models import HandoffRequest
from app.db.session import get_db_session
from app.services.handoff_types import HandoffContext, HandoffReason

logger = logging.getLogger(__name__)


class HandoffServiceError(Exception):
    """Base exception for handoff service errors."""


@dataclass(slots=True)
class HandoffData:
    """Data structure for handoff requests."""

    tenant_id: UUID
    reason: HandoffReason
    context: HandoffContext
    id: UUID = field(default_factory=uuid7)

    # Core identifiers
    flow_id: UUID | None = None
    thread_id: UUID | None = None
    contact_id: UUID | None = None
    channel_instance_id: UUID | None = None
    session_id: str | None = None

    # Snapshot of state at handoff time
    current_node_id: str | None = None
    user_message: str | None = None
    collected_answers: dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "id": str(self.id),
            "tenant_id": str(self.tenant_id),
            "reason": self.reason.model_dump(),
            "context": self.context.model_dump(),
            "flow_id": str(self.flow_id) if self.flow_id else None,
            "thread_id": str(self.thread_id) if self.thread_id else None,
            "contact_id": str(self.contact_id) if self.contact_id else None,
            "channel_instance_id": str(self.channel_instance_id)
            if self.channel_instance_id
            else None,
            "current_node_id": self.current_node_id,
            "user_message": self.user_message,
            "collected_answers": self.collected_answers,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffData:
        """Create from dictionary (Redis retrieval)."""
        return cls(
            id=UUID(data["id"]),
            tenant_id=UUID(data["tenant_id"]),
            reason=HandoffReason.model_validate(data.get("reason", {})),
            context=HandoffContext.model_validate(data.get("context", {})),
            flow_id=UUID(data["flow_id"]) if data.get("flow_id") else None,
            thread_id=UUID(data["thread_id"]) if data.get("thread_id") else None,
            contact_id=UUID(data["contact_id"]) if data.get("contact_id") else None,
            channel_instance_id=UUID(data["channel_instance_id"])
            if data.get("channel_instance_id")
            else None,
            current_node_id=data.get("current_node_id"),
            user_message=data.get("user_message"),
            collected_answers=data.get("collected_answers", {}),
            session_id=data.get("session_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


class HandoffService:
    """
    Robust handoff tracking service.

    Implements a database-first, Redis-fallback strategy with Tenacity retries
    to ensure handoff requests are never lost.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.REDIS_EXPIRY_DAYS = 180
        self.REDIS_EXPIRY_SECONDS = self.REDIS_EXPIRY_DAYS * 24 * 60 * 60

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((SQLAlchemyError, ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
    )
    def _save_to_database(self, handoff_data: HandoffData) -> bool:
        """Save handoff request to database with retry logic."""
        try:
            with next(get_db_session()) as session:
                handoff_request = HandoffRequest(
                    id=handoff_data.id,
                    tenant_id=handoff_data.tenant_id,
                    flow_id=handoff_data.flow_id,
                    thread_id=handoff_data.thread_id,
                    contact_id=handoff_data.contact_id,
                    channel_instance_id=handoff_data.channel_instance_id,
                    reason=handoff_data.reason.model_dump(),
                    current_node_id=handoff_data.current_node_id,
                    user_message=handoff_data.user_message,
                    collected_answers=handoff_data.collected_answers,
                    session_id=handoff_data.session_id,
                    conversation_context=handoff_data.context.model_dump(),
                )

                session.add(handoff_request)
                session.commit()

                logger.info(
                    "Successfully saved handoff request to database: %s (tenant: %s)",
                    handoff_data.id,
                    handoff_data.tenant_id,
                )
                return True

        except Exception as e:
            logger.error(
                "Failed to save handoff request %s to database: %s",
                handoff_data.id,
                str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=0.5, min=1, max=5),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
    )
    def _save_to_redis(self, handoff_data: HandoffData) -> bool:
        """Save handoff request to Redis with retry logic."""
        if not self.redis:
            logger.warning("Redis client not available for handoff backup")
            return False

        try:
            redis_key = redis_keys.handoff_request_key(str(handoff_data.id))
            handoff_json = json.dumps(handoff_data.to_dict(), ensure_ascii=False)

            # Set with expiration (180 days)
            self.redis.setex(
                redis_key,
                self.REDIS_EXPIRY_SECONDS,
                handoff_json,
            )

            # Also add to tenant's handoff list for easy retrieval
            tenant_list_key = redis_keys.tenant_handoffs_key(str(handoff_data.tenant_id))
            self.redis.lpush(tenant_list_key, str(handoff_data.id))
            self.redis.expire(tenant_list_key, self.REDIS_EXPIRY_SECONDS)

            logger.info(
                "Successfully saved handoff request to Redis backup: %s (tenant: %s)",
                handoff_data.id,
                handoff_data.tenant_id,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to save handoff request %s to Redis: %s",
                handoff_data.id,
                str(e),
            )
            raise

    def save_handoff_request(self, handoff_data: HandoffData) -> bool:
        """
        Save handoff request with database-first, Redis-fallback strategy.

        Returns True if saved to at least one storage system.
        """
        database_success = False
        redis_success = False

        # Try database first
        try:
            database_success = self._save_to_database(handoff_data)
        except Exception as e:
            logger.warning(
                "Database save failed for handoff %s, will try Redis fallback: %s",
                handoff_data.id,
                str(e),
            )

        # Try Redis fallback if database failed or as additional backup
        try:
            redis_success = self._save_to_redis(handoff_data)
        except Exception as e:
            logger.error(
                "Redis fallback also failed for handoff %s: %s",
                handoff_data.id,
                str(e),
            )

        # Success if either storage method worked
        if database_success or redis_success:
            storage_methods = []
            if database_success:
                storage_methods.append("database")
            if redis_success:
                storage_methods.append("redis")

            logger.info(
                "Handoff request %s saved successfully to: %s",
                handoff_data.id,
                ", ".join(storage_methods),
            )
            return True
        # This is critical - we couldn't save anywhere
        logger.critical(
            "CRITICAL: Failed to save handoff request %s to both database and Redis! "
            "Manual intervention required. Data: %s",
            handoff_data.id,
            handoff_data.to_dict(),
        )
        raise HandoffServiceError(
            f"Failed to save handoff request {handoff_data.id} to any storage system"
        )

    def get_handoff_requests(
        self,
        tenant_id: UUID,
        acknowledged: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HandoffRequest]:
        """Get handoff requests from database."""
        try:
            with next(get_db_session()) as session:
                query = session.query(HandoffRequest).filter(HandoffRequest.tenant_id == tenant_id)

                if acknowledged is not None:
                    if acknowledged:
                        query = query.filter(HandoffRequest.acknowledged_at.is_not(None))
                    else:
                        query = query.filter(HandoffRequest.acknowledged_at.is_(None))

                query = query.order_by(HandoffRequest.created_at.desc())
                query = query.offset(offset).limit(limit)

                return query.all()

        except Exception as e:
            logger.error("Failed to retrieve handoff requests: %s", str(e))
            raise HandoffServiceError(f"Failed to retrieve handoff requests: {e}")

    def acknowledge_handoff(self, handoff_id: UUID) -> bool:
        """Mark a handoff request as acknowledged."""
        try:
            with next(get_db_session()) as session:
                handoff = (
                    session.query(HandoffRequest).filter(HandoffRequest.id == handoff_id).first()
                )

                if not handoff:
                    logger.warning("Handoff request %s not found for acknowledgment", handoff_id)
                    return False

                handoff.acknowledged_at = datetime.utcnow()
                session.commit()

                logger.info("Handoff request %s acknowledged", handoff_id)
                return True

        except Exception as e:
            logger.error("Failed to acknowledge handoff %s: %s", handoff_id, str(e))
            raise HandoffServiceError(f"Failed to acknowledge handoff: {e}")
