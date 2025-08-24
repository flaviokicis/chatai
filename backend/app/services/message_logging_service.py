from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.db import repository
from app.db.models import MessageDirection, MessageStatus
from app.db.session import create_session

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class MessageLoggingService:
    """
    Async service for logging messages with retry logic and error handling.

    This service ensures all conversations are logged without blocking the main flow.
    It handles database errors gracefully and retries failed operations.
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def save_message_async(
        self,
        *,
        tenant_id: UUID,
        channel_instance_id: UUID,
        thread_id: UUID,
        contact_id: UUID | None,
        text: str | None,
        direction: MessageDirection,
        provider_message_id: str | None = None,
        payload: dict | None = None,
        status: MessageStatus = MessageStatus.sent,
        sent_at: datetime | None = None,
        delivered_at: datetime | None = None,
        read_at: datetime | None = None,
    ) -> None:
        """
        Save a message asynchronously with retry logic.

        This method runs in a separate task and doesn't block the main flow.
        If it fails, it logs the error but doesn't raise exceptions.
        """
        # Run the database operation in a thread pool to avoid blocking
        asyncio.create_task(
            self._save_message_with_retry(
                tenant_id=tenant_id,
                channel_instance_id=channel_instance_id,
                thread_id=thread_id,
                contact_id=contact_id,
                text=text,
                direction=direction,
                provider_message_id=provider_message_id,
                payload=payload,
                status=status,
                sent_at=sent_at,
                delivered_at=delivered_at,
                read_at=read_at,
            )
        )

    async def _save_message_with_retry(
        self,
        *,
        tenant_id: UUID,
        channel_instance_id: UUID,
        thread_id: UUID,
        contact_id: UUID | None,
        text: str | None,
        direction: MessageDirection,
        provider_message_id: str | None = None,
        payload: dict | None = None,
        status: MessageStatus = MessageStatus.sent,
        sent_at: datetime | None = None,
        delivered_at: datetime | None = None,
        read_at: datetime | None = None,
    ) -> None:
        """Internal method that handles retry logic."""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                # Create a new session for each attempt
                session = create_session()
                try:
                    repository.create_message(
                        session,
                        tenant_id=tenant_id,
                        channel_instance_id=channel_instance_id,
                        thread_id=thread_id,
                        contact_id=contact_id,
                        text=text,
                        direction=direction,
                        provider_message_id=provider_message_id,
                        payload=payload,
                        status=status,
                        sent_at=sent_at,
                        delivered_at=delivered_at,
                        read_at=read_at,
                    )
                    session.commit()

                    # Log success (only on retry attempts or errors)
                    if attempt > 0:  # Only log if this was a retry attempt
                        direction_str = (
                            "inbound" if direction == MessageDirection.inbound else "outbound"
                        )
                        logger.info(
                            f"Successfully saved {direction_str} message for tenant {tenant_id}, "
                            f"thread {thread_id}, attempt {attempt + 1}"
                        )
                    return  # Success - exit retry loop

                finally:
                    session.close()

            except SQLAlchemyError as e:
                last_exception = e
                logger.warning(
                    f"Database error saving message (attempt {attempt + 1}/{self.max_retries}): {e}"
                )

                if attempt < self.max_retries - 1:
                    # Wait before retrying (exponential backoff)
                    wait_time = self.retry_delay * (2**attempt)
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error saving message (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    await asyncio.sleep(wait_time)

        # All retries failed
        direction_str = "inbound" if direction == MessageDirection.inbound else "outbound"
        logger.error(
            f"Failed to save {direction_str} message after {self.max_retries} attempts. "
            f"Last error: {last_exception}. "
            f"Tenant: {tenant_id}, Thread: {thread_id}"
        )

    async def save_conversation_batch_async(
        self,
        messages: Sequence[dict],
    ) -> None:
        """
        Save multiple messages as a batch operation.

        This method is useful when you need to save both inbound and outbound
        messages from the same conversation turn.
        """
        tasks = []
        for msg_data in messages:
            task = self._save_message_with_retry(**msg_data)
            tasks.append(task)

        # Run all saves concurrently
        await asyncio.gather(*tasks, return_exceptions=True)


# Global service instance
message_logging_service = MessageLoggingService()
