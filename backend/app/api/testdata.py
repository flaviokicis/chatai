from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.base import Base
from app.db.models import TestItem
from app.db.session import get_db_session

router = APIRouter(prefix="/testdata", tags=["testdata"])


class TestItemModel(BaseModel):
    id: int
    content: str
    created_at: datetime


class CreateTestItemRequest(BaseModel):
    content: str = Field(min_length=1, max_length=255)


class TestItemResponse(TestItemModel):
    pass


@router.post("/", response_model=TestItemResponse)
def create_test_item(
    payload: CreateTestItemRequest,
    session=Depends(get_db_session),
) -> Any:
    try:
        # Ensure tables exist on first use
        Base.metadata.create_all(bind=session.get_bind())
        item = TestItem(content=payload.content, created_at=datetime.now(UTC))
        session.add(item)
        session.commit()
        session.refresh(item)
        return TestItemResponse(id=item.id, content=item.content, created_at=item.created_at)
    except Exception as exc:  # pragma: no cover - surfaced as 500 in API
        session.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc


@router.get("/", response_model=list[TestItemResponse])
def list_test_items(session=Depends(get_db_session)) -> Any:
    try:
        Base.metadata.create_all(bind=session.get_bind())
        rows: list[TestItem] = session.query(TestItem).order_by(TestItem.id.desc()).limit(100).all()
        return [TestItemResponse(id=r.id, content=r.content, created_at=r.created_at) for r in rows]
    except Exception as exc:  # pragma: no cover - surfaced as 500 in API
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc
