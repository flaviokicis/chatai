from __future__ import annotations

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.channels import router as channels_router
from app.api.chats import router as chats_router
from app.api.flow_chat import router as flow_chat_router
from app.api.flow_chat import router_versions as flow_versions_router
from app.api.flows import router as flows_router
from app.api.handoffs import router as handoffs_router
from app.api.tenant_admin import router as tenant_admin_router
from app.api.tenants import router as tenants_router
from app.whatsapp.router import router as whatsapp_router

api_router = APIRouter(prefix="/api")

# Mount channel/feature routers here
api_router.include_router(flows_router)
api_router.include_router(flow_chat_router)
api_router.include_router(flow_versions_router)
api_router.include_router(channels_router)  # User-accessible channel endpoints
api_router.include_router(whatsapp_router)
api_router.include_router(tenants_router)  # Public tenant endpoints
api_router.include_router(admin_router)    # Protected admin endpoints
api_router.include_router(tenant_admin_router)
api_router.include_router(chats_router)
api_router.include_router(handoffs_router)  # Human handoff tracking
