from __future__ import annotations

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.chats import router as chats_router
from app.api.flows import router as flows_router
from app.whatsapp.router import router as whatsapp_router

api_router = APIRouter()

# Mount channel/feature routers here
api_router.include_router(flows_router)
api_router.include_router(whatsapp_router)
api_router.include_router(admin_router)
api_router.include_router(chats_router)
