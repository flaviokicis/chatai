"""WhatsApp-specific thread status updater."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.flow_processor import (
    FlowProcessingResult,
    FlowRequest,
    FlowResponse,
    ThreadStatusUpdater,
)
from app.db.models import ThreadStatus
from app.db.session import create_session

if TYPE_CHECKING:
    from uuid import UUID

logger = logging.getLogger(__name__)


class WhatsAppThreadStatusUpdater(ThreadStatusUpdater):
    """WhatsApp-specific implementation of thread status updates."""

    def update_completion_status(
        self,
        thread_id: UUID,
        flow_response: FlowResponse,
        request: FlowRequest,
    ) -> None:
        """Update thread status after flow completion."""
        if flow_response.result not in [FlowProcessingResult.TERMINAL, FlowProcessingResult.ESCALATE]:
            return

        # Import ChatThread model here to avoid circular imports
        from app.db.models import ChatThread

        update_session = create_session()
        try:

            thread_for_update = update_session.get(ChatThread, thread_id)
            if not thread_for_update:
                logger.warning("Thread %s not found for completion update", thread_id)
                return

            if flow_response.result == FlowProcessingResult.ESCALATE:
                # Track human handoff request
                thread_for_update.human_handoff_requested_at = datetime.now(UTC)
                logger.info("Marked thread %s for human handoff", thread_for_update.id)

            if flow_response.result == FlowProcessingResult.TERMINAL and flow_response.context:
                # Store completion data and close thread
                thread_for_update.flow_completion_data = {
                    "answers": flow_response.context.answers,
                    "flow_id": request.flow_metadata.get("flow_id"),
                    "flow_name": request.flow_metadata.get("flow_name"),
                    "completion_message": flow_response.message,
                    "total_messages": len(getattr(flow_response.context, "history", [])),
                }
                thread_for_update.completed_at = datetime.now(UTC)
                thread_for_update.status = ThreadStatus.closed
                logger.info("Closed thread %s with completion data", thread_for_update.id)

            update_session.commit()

        except Exception:
            logger.exception("Failed to update thread with flow result")
            update_session.rollback()
            raise
        finally:
            update_session.close()
