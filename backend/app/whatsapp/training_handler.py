"""WhatsApp-specific training mode handler."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from app.core.flow_processor import (
    FlowProcessingResult,
    FlowRequest,
    FlowResponse,
    TrainingModeHandler,
)
from app.db.session import create_session
from app.services.training_mode_service import TrainingModeService

logger = logging.getLogger(__name__)


class WhatsAppTrainingHandler(TrainingModeHandler):
    """WhatsApp-specific implementation of training mode handling."""

    async def handle_training_request(
        self,
        request: FlowRequest,
        session_id: str,
        app_context: Any,
    ) -> FlowResponse | None:
        """Handle training mode if active, return None if not in training mode."""
        training_session = create_session()
        try:
            training = TrainingModeService(training_session, app_context)

            # Get thread from metadata
            thread_id = request.flow_metadata.get("thread_id")
            if not thread_id:
                return None

            # Import ChatThread model here to avoid circular imports
            from app.db.models import ChatThread
            thread_in_training = training_session.get(ChatThread, thread_id)

            if not thread_in_training:
                return None

            # Check if awaiting password
            if training.awaiting_password(thread_in_training, user_id=request.user_id):
                mock_flow = SimpleNamespace(
                    id=request.flow_metadata.get("selected_flow_id"),
                    flow_id=request.flow_metadata.get("flow_id"),
                    name=request.flow_metadata.get("flow_name")
                )
                handled, reply = training.validate_password(
                    thread_in_training,
                    mock_flow,
                    request.user_message,
                    user_id=request.user_id,
                    flow_session_key=session_id,
                )
                return FlowResponse(
                    result=FlowProcessingResult.TRAINING_MODE,
                    message=reply,
                    context=None,
                    metadata={"tool_name": "TrainingPasswordValidation"},
                )

            # Check if in active training mode
            if getattr(thread_in_training, "training_mode", False):
                try:
                    mock_flow = SimpleNamespace(
                        id=request.flow_metadata.get("selected_flow_id"),
                        flow_id=request.flow_metadata.get("flow_id"),
                        name=request.flow_metadata.get("flow_name"),
                        definition=request.flow_definition
                    )
                    reply_text = await training.handle_training_message(
                        thread_in_training,
                        mock_flow,
                        request.user_message,
                        request.project_context
                    )
                    return FlowResponse(
                        result=FlowProcessingResult.TRAINING_MODE,
                        message=reply_text,
                        context=None,
                        metadata={"tool_name": "TrainingMessageHandling"},
                    )
                except Exception as e:
                    logger.error("Training mode processing failed: %s", e)
                    return FlowResponse(
                        result=FlowProcessingResult.TRAINING_MODE,
                        message="Falha ao processar instrução de treino. Tente novamente.",
                        context=None,
                        metadata={"tool_name": "TrainingMessageHandling"},
                    )
        finally:
            training_session.close()

        return None
