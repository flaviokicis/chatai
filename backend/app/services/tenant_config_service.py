from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import repository

if TYPE_CHECKING:
    from app.db.models import Tenant

logger = logging.getLogger(__name__)


@dataclass
class ProjectContext:
    """
    Project context data for enhancing LLM prompts.

    This contains the business context that helps LLMs understand
    how to communicate and make decisions appropriately.
    """

    tenant_id: UUID
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None

    # Timing and response behavior configuration
    wait_time_before_replying_ms: int = 2000
    typing_indicator_enabled: bool = True
    min_typing_duration_ms: int = 1000
    max_typing_duration_ms: int = 5000
    message_reset_enabled: bool = True
    natural_delays_enabled: bool = True
    delay_variance_percent: int = 20

    def has_decision_context(self) -> bool:
        """Check if we have context for decision-making LLM."""
        return self.project_description is not None or self.target_audience is not None

    def has_rewriter_context(self) -> bool:
        """Check if we have context for rewriter LLM."""
        return (
            self.project_description is not None
            or self.target_audience is not None
            or self.communication_style is not None
        )

    def get_decision_context_prompt(self) -> str:
        """Generate context prompt for decision-making LLM."""
        if not self.has_decision_context():
            return ""

        parts = []
        if self.project_description:
            parts.append(f"Business context: {self.project_description}")
        if self.target_audience:
            parts.append(f"Target audience: {self.target_audience}")

        if not parts:
            return ""

        return f"\nBusiness Context for Decision Making:\n{' | '.join(parts)}\n"

    def get_rewriter_context_prompt(self) -> str:
        """Generate context prompt for rewriter LLM."""
        if not self.has_rewriter_context():
            return ""

        parts = []
        if self.project_description:
            parts.append(f"Business: {self.project_description}")
        if self.target_audience:
            parts.append(f"Audience: {self.target_audience}")
        if self.communication_style:
            parts.append(f"Style: {self.communication_style}")

        if not parts:
            return ""

        context_info = " | ".join(parts)
        style_instruction = ""

        if self.communication_style:
            style_instruction = f"\nIMPORTANT: Adapt your communication style to match: {self.communication_style}. Stay very close to this style example when rewriting."

        return f"\nBusiness Context: {context_info}{style_instruction}\n"


class TenantConfigService:
    """
    Service for retrieving tenant configuration and project context.

    This service centralizes the logic for getting tenant-specific settings
    that enhance AI behavior and decision-making.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_project_context_by_tenant_id(self, tenant_id: UUID) -> ProjectContext | None:
        """
        Get project context for a tenant by ID.

        Returns None if tenant doesn't exist or has no project config.
        """
        try:
            tenant = repository.get_tenant_by_id(self.session, tenant_id)
            if not tenant:
                logger.warning(f"Tenant {tenant_id} not found")
                return None

            return self._build_project_context(tenant)

        except Exception as e:
            logger.error(f"Error getting project context for tenant {tenant_id}: {e}")
            return None

    def get_project_context_by_channel_identifier(
        self, channel_identifier: str
    ) -> ProjectContext | None:
        """
        Get project context for a tenant by channel identifier (WhatsApp number).

        This is the main method used by the webhook handler.
        """
        try:
            # Find the channel instance first
            channel_instance = repository.find_channel_instance_by_identifier(
                self.session, channel_identifier
            )
            if not channel_instance:
                logger.warning(f"Channel instance not found for identifier: {channel_identifier}")
                return None

            # Get the tenant with project config
            tenant = repository.get_tenant_by_id(self.session, channel_instance.tenant_id)
            if not tenant:
                logger.warning(
                    f"Tenant {channel_instance.tenant_id} not found for channel {channel_identifier}"
                )
                return None

            return self._build_project_context(tenant)

        except Exception as e:
            logger.error(f"Error getting project context for channel {channel_identifier}: {e}")
            return None

    def _build_project_context(self, tenant: Tenant) -> ProjectContext:
        """Build ProjectContext from tenant and project config."""
        project_config = tenant.project_config

        return ProjectContext(
            tenant_id=tenant.id,
            project_description=project_config.project_description if project_config else None,
            target_audience=project_config.target_audience if project_config else None,
            communication_style=project_config.communication_style if project_config else None,
            wait_time_before_replying_ms=project_config.wait_time_before_replying_ms
            if project_config
            else 2000,
            typing_indicator_enabled=project_config.typing_indicator_enabled
            if project_config
            else True,
            min_typing_duration_ms=project_config.min_typing_duration_ms
            if project_config
            else 1000,
            max_typing_duration_ms=project_config.max_typing_duration_ms
            if project_config
            else 5000,
            message_reset_enabled=project_config.message_reset_enabled if project_config else True,
            natural_delays_enabled=project_config.natural_delays_enabled
            if project_config
            else True,
            delay_variance_percent=project_config.delay_variance_percent if project_config else 20,
        )
