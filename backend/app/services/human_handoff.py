from __future__ import annotations

import logging
from typing import Any

from app.core.tools import HumanHandoffTool

logger = logging.getLogger("uvicorn.error")


class LoggingHandoff(HumanHandoffTool):
    def escalate(self, user_id: str, reason: str, summary: dict[str, Any]) -> None:  # type: ignore[override]
        logger.info("Escalation for %s: reason=%s summary=%s", user_id, reason, summary)
