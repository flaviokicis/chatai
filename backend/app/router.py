from __future__ import annotations

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.chats import router as chats_router
from app.api.flows import router as flows_router
from app.api.flow_chat import router as flow_chat_router, router_versions as flow_versions_router
from app.whatsapp.router import router as whatsapp_router

api_router = APIRouter(prefix="/api")

# Mount channel/feature routers here
api_router.include_router(flows_router)
api_router.include_router(flow_chat_router)
api_router.include_router(flow_versions_router)
api_router.include_router(whatsapp_router)
api_router.include_router(admin_router)
api_router.include_router(chats_router)
