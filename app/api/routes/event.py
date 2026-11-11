from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.event import EventListOut, EventOut
from app.repos import event_repo

router = APIRouter(prefix="/events", tags=["events"])


#返回事件流
@router.get("", response_model=EventListOut, summary="事件流")
async def list_events(
    player_id: int = Query(..., ge=1),
    limit: int = Query(20, ge=1, le=100),
    before_id: int | None = Query(None, ge=1),
    event_type: str | None = Query(None, max_length=32),      # ← 新增这一行
    session: AsyncSession = Depends(get_session),
) -> EventListOut:
    rows = await event_repo.list_recent(
        session,
        player_id=player_id,
        event_type=event_type,                                 # ← 传下去
        limit=limit,
        before_id=before_id,
    )
    return EventListOut(
        total=len(rows),
        items=[EventOut.model_validate(r) for r in rows],
        next_before_id=rows[-1].id if len(rows) == limit else None,
    )