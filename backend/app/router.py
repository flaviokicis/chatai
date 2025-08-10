from __future__ import annotations

from fastapi import APIRouter

from app.whatsapp.router import router as whatsapp_router

api_router = APIRouter()

# Mount channel/feature routers here
api_router.include_router(whatsapp_router)
