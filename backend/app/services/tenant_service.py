from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import repository
from app.db.models import ChannelInstance, ChannelType, Flow, Tenant

logger = logging.getLogger(__name__)


class TenantServiceError(Exception):
    """Base exception for tenant service errors."""


class TenantNotFoundError(TenantServiceError):
    """Raised when a tenant is not found."""


class DuplicateChannelError(TenantServiceError):
    """Raised when trying to create a duplicate channel instance."""


class TenantService:
    """Service layer for tenant management operations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_tenant(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        project_description: str | None = None,
        target_audience: str | None = None,
        communication_style: str | None = None,
    ) -> Tenant:
        """Create a new tenant with project configuration."""
        try:
            tenant = repository.create_tenant_with_config(
                self.session,
                first_name=first_name,
                last_name=last_name,
                email=email,
                project_description=project_description,
                target_audience=target_audience,
                communication_style=communication_style,
            )
            self.session.commit()
            logger.info("Created tenant %s (%s %s)", str(tenant.id), first_name, last_name)
            return tenant
        except IntegrityError as exc:
            self.session.rollback()
            logger.error("Failed to create tenant: %s", exc)
            raise TenantServiceError("Failed to create tenant") from exc

    def get_all_tenants(self) -> Sequence[Tenant]:
        """Get all active tenants."""
        return repository.get_active_tenants(self.session)

    def get_tenant_by_id(self, tenant_id: UUID) -> Tenant:
        """Get tenant by ID, raising error if not found."""
        tenant = repository.get_tenant_by_id(self.session, tenant_id)
        if not tenant:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        return tenant

    def update_tenant_config(
        self,
        *,
        tenant_id: UUID,
        project_description: str | None = None,
        target_audience: str | None = None,
        communication_style: str | None = None,
    ) -> Tenant:
        """Update tenant project configuration."""
        try:
            tenant = repository.update_tenant_project_config(
                self.session,
                tenant_id=tenant_id,
                project_description=project_description,
                target_audience=target_audience,
                communication_style=communication_style,
            )
            if not tenant:
                raise TenantNotFoundError(f"Tenant {tenant_id} not found")

            self.session.commit()
            logger.info("Updated project config for tenant %s", str(tenant_id))
            return tenant
        except IntegrityError as exc:
            self.session.rollback()
            logger.error("Failed to update tenant config: %s", exc)
            raise TenantServiceError("Failed to update tenant configuration") from exc

    def create_channel_instance(
        self,
        *,
        tenant_id: UUID,
        channel_type: ChannelType,
        identifier: str,
        phone_number: str | None = None,
        extra: dict | None = None,
    ) -> ChannelInstance:
        """Create a new channel instance for a tenant."""
        # Verify tenant exists
        self.get_tenant_by_id(tenant_id)

        try:
            channel = repository.create_channel_instance(
                self.session,
                tenant_id=tenant_id,
                channel_type=channel_type.value,
                identifier=identifier,
                phone_number=phone_number,
                extra=extra,
            )
            self.session.commit()
            logger.info(
                "Created channel instance %s for tenant %s", str(channel.id), str(tenant_id)
            )
            return channel
        except IntegrityError as exc:
            self.session.rollback()
            logger.error("Failed to create channel instance: %s", exc)
            raise DuplicateChannelError("Channel identifier already exists") from exc

    def get_channel_instances(self, tenant_id: UUID) -> Sequence[ChannelInstance]:
        """Get all channel instances for a tenant."""
        # Verify tenant exists
        self.get_tenant_by_id(tenant_id)
        return repository.get_channel_instances_by_tenant(self.session, tenant_id)

    def create_flow(
        self,
        *,
        tenant_id: UUID,
        channel_instance_id: UUID,
        name: str,
        flow_id: str,
        definition: dict,
    ) -> Flow:
        """Create a new flow for a tenant."""
        # Verify tenant exists
        self.get_tenant_by_id(tenant_id)

        try:
            flow = repository.create_flow(
                self.session,
                tenant_id=tenant_id,
                channel_instance_id=channel_instance_id,
                name=name,
                flow_id=flow_id,
                definition=definition,
            )
            self.session.commit()
            logger.info("Created flow %s (%s) for tenant %s", str(flow.id), name, str(tenant_id))
            return flow
        except IntegrityError as exc:
            self.session.rollback()
            logger.error("Failed to create flow: %s", exc)
            raise TenantServiceError("Failed to create flow") from exc

    def get_flows(self, tenant_id: UUID) -> Sequence[Flow]:
        """Get all flows for a tenant."""
        # Verify tenant exists
        self.get_tenant_by_id(tenant_id)
        return repository.get_flows_by_tenant(self.session, tenant_id)

    def update_flow(
        self,
        *,
        tenant_id: UUID,
        flow_id: UUID,
        name: str | None = None,
        definition: dict | None = None,
        is_active: bool | None = None,
    ) -> Flow:
        """Update an existing flow for a tenant."""
        # Verify tenant exists
        self.get_tenant_by_id(tenant_id)

        # Get the flow and verify it belongs to the tenant
        flow = repository.get_flow_by_id(self.session, flow_id)
        if not flow:
            raise TenantServiceError(f"Flow {flow_id} not found")
        
        if flow.tenant_id != tenant_id:
            raise TenantServiceError(f"Flow {flow_id} does not belong to tenant {tenant_id}")

        try:
            updated_flow = repository.update_flow(
                self.session,
                flow_id=flow_id,
                name=name,
                definition=definition,
                is_active=is_active,
            )
            if not updated_flow:
                raise TenantServiceError(f"Failed to update flow {flow_id}")

            self.session.commit()
            logger.info("Updated flow %s for tenant %s", str(flow_id), str(tenant_id))
            return updated_flow
        except IntegrityError as exc:
            self.session.rollback()
            logger.error("Failed to update flow: %s", exc)
            raise TenantServiceError("Failed to update flow") from exc
