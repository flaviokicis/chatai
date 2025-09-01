"""
Admin API endpoints for tenant and database management.

Requires ADMIN_PASSWORD environment variable for authentication.
Provides CRUD operations for tenants, channels, and flows with proper cascade deletes.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.app_context import get_app_context
from app.core.state import RedisStore
from app.core.thought_tracer import DatabaseThoughtTracer
from app.db.models import ChannelType
from app.db.repository import (
    create_channel_instance,
    create_tenant_with_config,
    delete_tenant_cascade,
    get_active_tenants,
    get_channel_instances_by_tenant,
    get_flow_by_id,
    get_flows_by_tenant,
    get_tenant_by_id,
    update_flow_definition,
    update_tenant,
)
from app.db.session import db_session
from app.settings import get_settings
from app.core.redis_keys import redis_keys

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/controller", tags=["controller"])
security = HTTPBearer()


# Pydantic models for API
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    success: bool
    message: str
    expires_at: datetime | None = None


class TenantCreateRequest(BaseModel):
    owner_first_name: str = Field(..., min_length=1, max_length=120)
    owner_last_name: str = Field(..., min_length=1, max_length=120)
    owner_email: str = Field(..., min_length=1)
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None


class TenantUpdateRequest(BaseModel):
    owner_first_name: str | None = Field(None, min_length=1, max_length=120)
    owner_last_name: str | None = Field(None, min_length=1, max_length=120)
    owner_email: str | None = Field(None, min_length=1)
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None


class ChannelCreateRequest(BaseModel):
    channel_type: ChannelType
    identifier: str = Field(..., min_length=1)
    phone_number: str | None = None
    extra: dict[str, Any] | None = None


class FlowUpdateRequest(BaseModel):
    definition: dict[str, Any]


class FlowTrainingPasswordRequest(BaseModel):
    training_password: str = Field(..., min_length=1, max_length=50)


class TenantResponse(BaseModel):
    id: UUID
    owner_first_name: str
    owner_last_name: str
    owner_email: str
    created_at: datetime
    updated_at: datetime
    project_description: str | None = None
    target_audience: str | None = None
    communication_style: str | None = None
    channel_count: int
    flow_count: int


class ChannelResponse(BaseModel):
    id: UUID
    channel_type: ChannelType
    identifier: str
    phone_number: str | None
    extra: dict[str, Any] | None
    created_at: datetime


class FlowResponse(BaseModel):
    id: UUID
    name: str
    flow_id: str
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None = None
    training_password: str | None = None


class ConversationInfo(BaseModel):
    user_id: str
    agent_type: str  # Proper agent type: "flow", "chat", etc.
    session_id: str
    last_activity: datetime | None = None
    message_count: int = 0
    is_active: bool = False
    tenant_id: str | None = None
    is_historical: bool = False  # True if from database (completed), False if from Redis (active)
    flow_name: str | None = None  # Flow identifier for display (e.g., "flow.atendimento_luminarias")


class ConversationsResponse(BaseModel):
    conversations: list[ConversationInfo]
    total_count: int
    active_count: int


class ResetConversationRequest(BaseModel):
    user_id: str
    agent_type: str | None = None  # If None, reset all agent types for this user


class AgentThoughtResponse(BaseModel):
    id: str
    timestamp: str
    user_message: str
    reasoning: str
    selected_tool: str
    tool_args: dict[str, Any]
    tool_result: str | None = None
    agent_response: str | None = None
    errors: list[str] | None = None
    confidence: float | None = None
    processing_time_ms: int | None = None
    model_name: str


class ConversationTraceResponse(BaseModel):
    user_id: str
    session_id: str
    agent_type: str
    started_at: str
    last_activity: str
    total_thoughts: int
    thoughts: list[AgentThoughtResponse]
    channel_id: str | None = None  # Channel identifier for customer traceability


class AllTracesResponse(BaseModel):
    traces: list[ConversationTraceResponse]
    total_count: int


# Authentication helpers
def get_admin_credentials() -> tuple[str, str]:
    """Get admin username and password from settings."""
    settings = get_settings()

    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin authentication not configured. Set ADMIN_PASSWORD environment variable."
        )

    return settings.admin_username, settings.admin_password


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    # Check for forwarded IP first (for reverse proxy setups)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in case of multiple proxies
        return forwarded_for.split(",")[0].strip()

    # Check for real IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, ip_address: str) -> tuple[bool, int]:
    """
    Check if IP address has exceeded login attempt rate limit.
    
    Returns:
        tuple[bool, int]: (is_allowed, remaining_cooldown_seconds)
    """
    app_context = get_app_context(request.app)  # type: ignore[arg-type]

    # If no Redis available, allow (fail open for availability)
    if not isinstance(app_context.store, RedisStore):
        return True, 0

    redis_client = app_context.store._r
    namespace = app_context.store._ns

    # Rate limiting keys
    attempts_key = f"{namespace}:admin_login_attempts:{ip_address}"
    cooldown_key = f"{namespace}:admin_login_cooldown:{ip_address}"

    try:
        # Check if IP is in cooldown
        cooldown_expiry = redis_client.get(cooldown_key)
        if cooldown_expiry:
            remaining = int(cooldown_expiry.decode()) - int(time.time())
            if remaining > 0:
                return False, remaining

        # Check attempt count
        attempts = redis_client.get(attempts_key)
        current_attempts = int(attempts.decode()) if attempts else 0

        # Allow if under limit
        if current_attempts < 3:
            return True, 0

        # Start cooldown if at limit
        cooldown_duration = 60  # 60 seconds
        cooldown_expiry_time = int(time.time()) + cooldown_duration
        redis_client.setex(cooldown_key, cooldown_duration, str(cooldown_expiry_time))

        return False, cooldown_duration

    except Exception as e:
        # Log error but fail open for availability
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Rate limiting check failed: %s", e)
        return True, 0


def record_failed_attempt(request: Request, ip_address: str) -> None:
    """Record a failed login attempt for rate limiting."""
    app_context = get_app_context(request.app)  # type: ignore[arg-type]

    # If no Redis available, skip recording
    if not isinstance(app_context.store, RedisStore):
        return

    redis_client = app_context.store._r
    namespace = app_context.store._ns

    attempts_key = f"{namespace}:admin_login_attempts:{ip_address}"

    try:
        # Increment attempt counter with 5 minute expiry
        redis_client.incr(attempts_key)
        redis_client.expire(attempts_key, 300)  # 5 minutes
    except Exception as e:
        # Log error but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Failed to record login attempt: %s", e)


def clear_rate_limit(request: Request, ip_address: str) -> None:
    """Clear rate limit for successful login."""
    app_context = get_app_context(request.app)  # type: ignore[arg-type]

    # If no Redis available, skip
    if not isinstance(app_context.store, RedisStore):
        return

    redis_client = app_context.store._r
    namespace = app_context.store._ns

    attempts_key = f"{namespace}:admin_login_attempts:{ip_address}"
    cooldown_key = f"{namespace}:admin_login_cooldown:{ip_address}"

    try:
        # Clear both attempt counter and cooldown
        redis_client.delete(attempts_key, cooldown_key)
    except Exception as e:
        # Log error but don't fail the request
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Failed to clear rate limit: %s", e)


def verify_admin_session(request: Request) -> bool:
    """Verify admin session is valid."""
    session = request.session
    is_admin = session.get("is_admin", False)
    expires_at = session.get("admin_expires_at")

    if not is_admin or not expires_at:
        return False

    try:
        expire_time = datetime.fromisoformat(expires_at)
        return datetime.now() < expire_time
    except (ValueError, TypeError):
        return False


def require_admin_auth(request: Request) -> None:
    """Dependency to require admin authentication."""
    if not verify_admin_session(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required"
        )


def get_db() -> Generator[Session, None, None]:
    """Database session dependency with proper resource management."""
    with db_session() as session:
        yield session


# API endpoints
@router.post("/auth", response_model=AdminLoginResponse)
async def admin_login(request: Request, login_req: AdminLoginRequest) -> AdminLoginResponse:
    """Authenticate admin user with secure password comparison and rate limiting."""
    import logging
    logger = logging.getLogger(__name__)

    # Get client IP for rate limiting
    client_ip = get_client_ip(request)

    # Check rate limiting
    is_allowed, cooldown_remaining = check_rate_limit(request, client_ip)
    if not is_allowed:
        logger.warning("Admin login rate limited for IP %s, %d seconds remaining", client_ip, cooldown_remaining)
        return AdminLoginResponse(
            success=False,
            message=f"Too many failed attempts. Please try again in {cooldown_remaining} seconds."
        )

    # Get admin credentials
    try:
        admin_username, admin_password = get_admin_credentials()
    except HTTPException:
        return AdminLoginResponse(success=False, message="Admin authentication not configured")

    # SECURITY: Use constant-time comparison to prevent timing attacks
    username_valid = hmac.compare_digest(
        login_req.username.encode("utf-8"),
        admin_username.encode("utf-8")
    )
    password_valid = hmac.compare_digest(
        login_req.password.encode("utf-8"),
        admin_password.encode("utf-8")
    )

    # Both username and password must be valid
    if not (username_valid and password_valid):
        # Record failed attempt for rate limiting
        record_failed_attempt(request, client_ip)
        logger.warning("Failed admin login attempt from IP %s with username '%s'", client_ip, login_req.username)
        return AdminLoginResponse(success=False, message="Invalid username or password")

    # Clear rate limiting on successful login
    clear_rate_limit(request, client_ip)

    # Set session with 24 hour expiry
    expires_at = datetime.now() + timedelta(hours=24)
    request.session["is_admin"] = True
    request.session["admin_expires_at"] = expires_at.isoformat()
    request.session["admin_username"] = admin_username  # Store for audit logging

    logger.info("Successful admin login for user '%s' from IP %s", admin_username, client_ip)

    return AdminLoginResponse(
        success=True,
        message="Authentication successful",
        expires_at=expires_at
    )


@router.post("/logout")
async def admin_logout(request: Request) -> dict[str, str]:
    """Logout admin user with audit logging."""
    import logging
    logger = logging.getLogger(__name__)

    # Log logout for audit trail
    client_ip = get_client_ip(request)
    admin_username = request.session.get("admin_username", "unknown")

    request.session.clear()

    logger.info("Admin logout for user '%s' from IP %s", admin_username, client_ip)
    return {"message": "Logged out successfully"}


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    request: Request,
    db: Session = Depends(get_db)
) -> list[TenantResponse]:
    """List all tenants with summary information."""
    require_admin_auth(request)

    tenants = get_active_tenants(db)
    result = []

    for tenant in tenants:
        channels = get_channel_instances_by_tenant(db, tenant.id)
        flows = get_flows_by_tenant(db, tenant.id)

        result.append(TenantResponse(
            id=tenant.id,
            owner_first_name=tenant.owner_first_name,
            owner_last_name=tenant.owner_last_name,
            owner_email=tenant.owner_email,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            project_description=tenant.project_config.project_description if tenant.project_config else None,
            target_audience=tenant.project_config.target_audience if tenant.project_config else None,
            communication_style=tenant.project_config.communication_style if tenant.project_config else None,
            channel_count=len(channels),
            flow_count=len(flows)
        ))

    return result


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    request: Request,
    tenant_req: TenantCreateRequest,
    db: Session = Depends(get_db)
) -> TenantResponse:
    """Create a new tenant."""
    require_admin_auth(request)

    try:
        tenant = create_tenant_with_config(
            db,
            first_name=tenant_req.owner_first_name,
            last_name=tenant_req.owner_last_name,
            email=tenant_req.owner_email,
            project_description=tenant_req.project_description,
            target_audience=tenant_req.target_audience,
            communication_style=tenant_req.communication_style
        )
        db.commit()

        return TenantResponse(
            id=tenant.id,
            owner_first_name=tenant.owner_first_name,
            owner_last_name=tenant.owner_last_name,
            owner_email=tenant.owner_email,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            project_description=tenant.project_config.project_description if tenant.project_config else None,
            target_audience=tenant.project_config.target_audience if tenant.project_config else None,
            communication_style=tenant.project_config.communication_style if tenant.project_config else None,
            channel_count=0,
            flow_count=0
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid data: {e!s}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Internal server error: {e!s}")


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant_endpoint(
    request: Request,
    tenant_id: UUID,
    tenant_req: TenantUpdateRequest,
    db: Session = Depends(get_db)
) -> TenantResponse:
    """Update a tenant."""
    require_admin_auth(request)

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        updated_tenant = update_tenant(
            db,
            tenant_id=tenant_id,
            first_name=tenant_req.owner_first_name,
            last_name=tenant_req.owner_last_name,
            email=tenant_req.owner_email,
            project_description=tenant_req.project_description,
            target_audience=tenant_req.target_audience,
            communication_style=tenant_req.communication_style
        )
        db.commit()

        channels = get_channel_instances_by_tenant(db, tenant_id)
        flows = get_flows_by_tenant(db, tenant_id)

        return TenantResponse(
            id=updated_tenant.id,
            owner_first_name=updated_tenant.owner_first_name,
            owner_last_name=updated_tenant.owner_last_name,
            owner_email=updated_tenant.owner_email,
            created_at=updated_tenant.created_at,
            updated_at=updated_tenant.updated_at,
            project_description=updated_tenant.project_config.project_description if updated_tenant.project_config else None,
            target_audience=updated_tenant.project_config.target_audience if updated_tenant.project_config else None,
            communication_style=updated_tenant.project_config.communication_style if updated_tenant.project_config else None,
            channel_count=len(channels),
            flow_count=len(flows)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tenants/{tenant_id}")
async def delete_tenant_endpoint(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """Delete a tenant and all associated data (cascading)."""
    require_admin_auth(request)

    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        delete_tenant_cascade(db, tenant_id)
        db.commit()
        return {"message": f"Tenant {tenant_id} and all associated data deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenants/{tenant_id}/channels", response_model=list[ChannelResponse])
async def list_tenant_channels(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> list[ChannelResponse]:
    """List channels for a tenant."""
    require_admin_auth(request)

    channels = get_channel_instances_by_tenant(db, tenant_id)
    return [
        ChannelResponse(
            id=channel.id,
            channel_type=channel.channel_type,
            identifier=channel.identifier,
            phone_number=channel.phone_number,
            extra=channel.extra,
            created_at=channel.created_at
        )
        for channel in channels
    ]


@router.post("/tenants/{tenant_id}/channels", response_model=ChannelResponse)
async def create_tenant_channel(
    request: Request,
    tenant_id: UUID,
    channel_req: ChannelCreateRequest,
    db: Session = Depends(get_db)
) -> ChannelResponse:
    """Create a new channel for a tenant."""
    require_admin_auth(request)

    # Verify tenant exists
    tenant = get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        channel = create_channel_instance(
            db,
            tenant_id=tenant_id,
            channel_type=channel_req.channel_type,
            identifier=channel_req.identifier,
            phone_number=channel_req.phone_number,
            extra=channel_req.extra
        )
        db.commit()

        return ChannelResponse(
            id=channel.id,
            channel_type=channel.channel_type,
            identifier=channel.identifier,
            phone_number=channel.phone_number,
            extra=channel.extra,
            created_at=channel.created_at
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tenants/{tenant_id}/flows", response_model=list[FlowResponse])
async def list_tenant_flows(
    request: Request,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> list[FlowResponse]:
    """List flows for a tenant."""
    require_admin_auth(request)

    flows = get_flows_by_tenant(db, tenant_id)
    return [
        FlowResponse(
            id=flow.id,
            name=flow.name,
            flow_id=flow.flow_id,
            definition=flow.definition,
            created_at=flow.created_at,
            updated_at=flow.updated_at,
            training_password=getattr(flow, "training_password", None),
        )
        for flow in flows
    ]


@router.put("/flows/{flow_id}", response_model=FlowResponse)
async def update_flow_endpoint(
    request: Request,
    flow_id: UUID,
    flow_req: FlowUpdateRequest,
    db: Session = Depends(get_db)
) -> FlowResponse:
    """Update a flow's definition (JSON editor)."""
    require_admin_auth(request)

    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    try:
        updated_flow = update_flow_definition(db, flow_id, flow_req.definition)
        db.commit()

        return FlowResponse(
            id=updated_flow.id,
            name=updated_flow.name,
            flow_id=updated_flow.flow_id,
            definition=updated_flow.definition,
            created_at=updated_flow.created_at,
            updated_at=updated_flow.updated_at,
            training_password=getattr(updated_flow, "training_password", None),
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/flows/{flow_id}/training-password")
async def get_flow_training_password(
    request: Request,
    flow_id: UUID,
    db: Session = Depends(get_db)
) -> dict[str, str | None]:
    """Get training password for a flow."""
    require_admin_auth(request)

    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    return {
        "flow_id": str(flow_id),
        "training_password": getattr(flow, "training_password", None),
    }


@router.put("/flows/{flow_id}/training-password")
async def update_flow_training_password(
    request: Request,
    flow_id: UUID,
    password_req: FlowTrainingPasswordRequest,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """Update training password for a flow."""
    require_admin_auth(request)

    flow = get_flow_by_id(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    try:
        flow.training_password = password_req.training_password
        db.commit()

        return {
            "message": "Training password updated successfully",
            "flow_id": str(flow_id),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
async def admin_health(request: Request) -> dict[str, str]:
    """Health check for admin API."""
    require_admin_auth(request)
    return {"status": "healthy", "service": "controller"}


@router.get("/conversations", response_model=ConversationsResponse)
async def list_conversations(
    request: Request,
    active_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> ConversationsResponse:
    """
    List all conversations with performance optimizations.
    
    Key optimizations:
    1. Single query with proper LIMIT
    2. Batch Redis lookups
    3. Reduced data transfer
    """
    require_admin_auth(request)

    try:
        from app.db.models import AgentConversationTrace
        from sqlalchemy import text
        
        # Single optimized query with proper indexing
        query = (
            db.query(AgentConversationTrace)
            .filter(AgentConversationTrace.deleted_at.is_(None))
            .order_by(AgentConversationTrace.last_activity_at.desc())
            .limit(limit * 2)  # Get extra for deduplication
        )
        
        all_traces = query.all()
        
        # Group by conversation (user_id + agent_type) for deduplication
        conversation_map = {}
        redis_keys_to_check = []
        
        for trace in all_traces:
            key = f"{trace.user_id}:{trace.agent_type}"
            
            if key not in conversation_map:
                conversation_map[key] = trace
                # Prepare Redis key for batch lookup
                user_parts = trace.user_id.split(":", 1)
                if len(user_parts) == 2:
                    channel, phone = user_parts
                    session_id = f"flow:{trace.user_id}:{trace.agent_type}"
                    state_key = redis_keys.conversation_state_key(channel, session_id)
                else:
                    state_key = redis_keys.conversation_state_key(trace.user_id, trace.agent_type)
                redis_keys_to_check.append((key, state_key))
        
        # Batch Redis lookup for active status
        active_status = {}
        app_context = get_app_context(request.app)  # type: ignore[arg-type]
        if isinstance(app_context.store, RedisStore):
            redis_client = app_context.store._r
            if redis_keys_to_check:
                # Use pipeline for batch Redis operations
                pipe = redis_client.pipeline()
                for _, redis_key in redis_keys_to_check:
                    pipe.exists(redis_key)
                results = pipe.execute()
                
                for i, (conv_key, _) in enumerate(redis_keys_to_check):
                    active_status[conv_key] = bool(results[i])
        
        # Build conversation list
        conversations = []
        for key, trace in conversation_map.items():
            is_active = active_status.get(key, False)
            
            # Skip inactive if active_only is True
            if active_only and not is_active:
                continue
                
            conversations.append(ConversationInfo(
                user_id=trace.user_id,
                agent_type=trace.agent_type,
                session_id=trace.session_id or f"{trace.user_id}:{trace.agent_type}",
                last_activity=trace.last_activity_at,
                message_count=trace.total_thoughts,
                is_active=is_active,
                tenant_id=str(trace.tenant_id),
                is_historical=not is_active
            ))
        
        # Sort by last activity and apply final limit
        conversations.sort(key=lambda x: x.last_activity or datetime.min, reverse=True)
        limited_conversations = conversations[:limit]
        active_count = sum(1 for conv in conversations if conv.is_active)
        
        return ConversationsResponse(
            conversations=limited_conversations,
            total_count=len(conversations),
            active_count=active_count
        )

    except Exception as e:
        logger.exception("Failed to retrieve conversations")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve conversations: {e!s}"
        )


@router.get("/conversations/stats")
async def get_conversation_stats(
    request: Request,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get conversation statistics without loading full data.
    Much faster for dashboard metrics.
    """
    require_admin_auth(request)
    
    try:
        # Use aggregation queries for fast stats
        stats_query = text("""
            SELECT 
                COUNT(*) as total_traces,
                COUNT(DISTINCT tenant_id) as unique_tenants,
                MAX(last_activity_at) as most_recent_activity,
                AVG(total_thoughts) as avg_thoughts_per_conversation
            FROM agent_conversation_traces 
            WHERE deleted_at IS NULL
        """)
        
        result = db.execute(stats_query).fetchone()
        
        return {
            "total_conversations": result.total_traces if result else 0,
            "unique_tenants": result.unique_tenants if result else 0,
            "most_recent_activity": result.most_recent_activity if result else None,
            "avg_thoughts_per_conversation": float(result.avg_thoughts_per_conversation) if result and result.avg_thoughts_per_conversation else 0.0
        }
        
    except Exception as e:
        logger.exception("Failed to get conversation stats")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get conversation stats: {e!s}"
        )


@router.get("/tenants/summary")
async def get_tenants_summary(
    request: Request,
    db: Session = Depends(get_db)
) -> dict[str, Any]:
    """
    Get tenant summary with optimized queries.
    """
    require_admin_auth(request)
    
    try:
        # Single query with aggregations
        tenants_query = text("""
            SELECT 
                t.id,
                t.owner_first_name,
                t.owner_last_name,
                t.created_at,
                COUNT(DISTINCT ci.id) as channel_count,
                COUNT(DISTINCT f.id) as flow_count
            FROM tenants t
            LEFT JOIN channel_instances ci ON t.id = ci.tenant_id AND ci.deleted_at IS NULL
            LEFT JOIN flows f ON t.id = f.tenant_id AND f.deleted_at IS NULL  
            WHERE t.deleted_at IS NULL
            GROUP BY t.id, t.owner_first_name, t.owner_last_name, t.created_at
            ORDER BY t.created_at DESC
        """)
        
        results = db.execute(tenants_query).fetchall()
        
        tenants_summary = []
        for row in results:
            tenants_summary.append({
                "id": str(row.id),
                "name": f"{row.owner_first_name} {row.owner_last_name}",
                "created_at": row.created_at,
                "channel_count": row.channel_count,
                "flow_count": row.flow_count
            })
        
        return {
            "tenants": tenants_summary,
            "total_tenants": len(tenants_summary)
        }
        
    except Exception as e:
        logger.exception("Failed to get tenants summary")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get tenants summary: {e!s}"
        )


@router.post("/conversations/reset")
async def reset_conversation_context(
    request: Request,
    reset_req: ResetConversationRequest
) -> dict[str, str]:
    """Reset conversation Redis context only (preserves debugging data)."""
    require_admin_auth(request)

    app_context = get_app_context(request.app)  # type: ignore[arg-type]
    if not isinstance(app_context.store, RedisStore):
        raise HTTPException(
            status_code=503,
            detail="Conversation management requires Redis storage"
        )

    try:
        redis_client = app_context.store._r
        deleted_keys = 0

        # Use the centralized key builder for consistent patterns
        if reset_req.agent_type:
            # Extract flow_id from agent_type if it's a flow
            flow_id = None
            if reset_req.agent_type.startswith("flow."):
                flow_id = reset_req.agent_type  # e.g., "flow.atendimento_luminarias"
            elif reset_req.agent_type.startswith("flow:"):
                # Handle the malformed agent_type we've been dealing with
                flow_id = reset_req.agent_type[5:]  # Remove "flow:" prefix
            
            patterns_to_delete = redis_keys.get_conversation_patterns(
                user_id=reset_req.user_id,
                flow_id=flow_id
            )
        else:
            # Reset all conversations for user
            patterns_to_delete = redis_keys.get_conversation_patterns(
                user_id=reset_req.user_id,
                flow_id=None
            )

        # Delete keys using patterns
        for pattern in patterns_to_delete:
            if "*" in pattern:
                # Use pattern matching for wildcard patterns
                keys = redis_client.keys(pattern)
                if keys:
                    deleted_count = redis_client.delete(*keys)
                    deleted_keys += deleted_count
                    logger.info(f"Deleted {deleted_count} keys matching pattern: {pattern}")
            else:
                # Direct key deletion
                if redis_client.exists(pattern):
                    redis_client.delete(pattern)
                    deleted_keys += 1
                    logger.info(f"Deleted direct key: {pattern}")

        # NOTE: We do NOT delete database records (ChatThreads, Messages, or Traces)
        # Those are valuable for debugging and customer support.
        # Reset only clears Redis context to allow conversation restart.
        
        flow_info = f" for flow '{reset_req.agent_type}'" if reset_req.agent_type else " for all flows"
        return {
            "message": f"Successfully reset Redis context for user '{reset_req.user_id}'{flow_info}",
            "deleted_keys": str(deleted_keys)
        }
        
    except Exception as e:
        logger.exception("Failed to reset conversation context")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset conversation: {e!s}"
        )


@router.get("/traces", response_model=AllTracesResponse)
async def list_all_traces(
    request: Request,
    limit: int = 50,
    tenant_id: UUID | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db)
) -> AllTracesResponse:
    """List all conversation traces with agent reasoning for a specific tenant."""
    require_admin_auth(request)

    # If no tenant_id provided, we need to get all tenants (admin can see all)
    # For now, require tenant_id to be explicit for security
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="tenant_id parameter is required"
        )

    try:
        thought_tracer = DatabaseThoughtTracer(db)
        traces = thought_tracer.get_all_traces(tenant_id, limit, active_only)

        # Convert to response format
        trace_responses = []
        for trace in traces:
            thought_responses = [
                AgentThoughtResponse(
                    id=thought.id,
                    timestamp=thought.timestamp,
                    user_message=thought.user_message,
                    reasoning=thought.reasoning,
                    selected_tool=thought.selected_tool,
                    tool_args=thought.tool_args,
                    tool_result=thought.tool_result,
                    agent_response=thought.agent_response,
                    errors=thought.errors,
                    confidence=thought.confidence,
                    processing_time_ms=thought.processing_time_ms,
                    model_name=thought.model_name
                )
                for thought in trace.thoughts
            ]

            trace_responses.append(ConversationTraceResponse(
                user_id=trace.user_id,
                session_id=trace.session_id,
                agent_type=trace.agent_type,
                started_at=trace.started_at,
                last_activity=trace.last_activity,
                total_thoughts=trace.total_thoughts,
                thoughts=thought_responses,
                channel_id=trace.channel_id
            ))

        return AllTracesResponse(
            traces=trace_responses,
            total_count=len(trace_responses)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve traces: {e!s}"
        )


@router.get("/traces/{agent_type}", response_model=ConversationTraceResponse)
async def get_conversation_trace(
    request: Request,
    agent_type: str,
    user_id: str = Query(...),
    tenant_id: UUID = Query(...),
    db: Session = Depends(get_db)
) -> ConversationTraceResponse:
    """Get detailed trace for a specific conversation."""
    require_admin_auth(request)

    # Debug logging to understand the path parameter parsing
    logger.info(f"Trace lookup request - user_id: '{user_id}', agent_type: '{agent_type}', tenant_id: {tenant_id}")

    try:
        thought_tracer = DatabaseThoughtTracer(db)
        trace = thought_tracer.get_conversation_trace(tenant_id, user_id, agent_type)

        if not trace:
            raise HTTPException(
                status_code=404,
                detail=f"No trace found for user '{user_id}' with agent type '{agent_type}'"
            )

        # Convert to response format
        thought_responses = [
            AgentThoughtResponse(
                id=thought.id,
                timestamp=thought.timestamp,
                user_message=thought.user_message,
                reasoning=thought.reasoning,
                selected_tool=thought.selected_tool,
                tool_args=thought.tool_args,
                tool_result=thought.tool_result,
                agent_response=thought.agent_response,
                errors=thought.errors,
                confidence=thought.confidence,
                processing_time_ms=thought.processing_time_ms,
                model_name=thought.model_name
            )
            for thought in trace.thoughts
        ]

        return ConversationTraceResponse(
            user_id=trace.user_id,
            session_id=trace.session_id,
            agent_type=trace.agent_type,
            started_at=trace.started_at,
            last_activity=trace.last_activity,
            total_thoughts=trace.total_thoughts,
            thoughts=thought_responses,
            channel_id=trace.channel_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve trace: {e!s}"
        )


@router.delete("/traces/{user_id}/{agent_type}")
async def clear_conversation_trace(
    request: Request,
    user_id: str,
    agent_type: str,
    tenant_id: UUID,
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """Clear the reasoning trace for a specific conversation."""
    require_admin_auth(request)

    try:
        thought_tracer = DatabaseThoughtTracer(db)
        success = thought_tracer.clear_trace(tenant_id, user_id, agent_type)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"No trace found for user '{user_id}' with agent type '{agent_type}'"
            )

        return {
            "message": f"Successfully cleared trace for user '{user_id}' with agent type '{agent_type}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear trace: {e!s}"
        )
