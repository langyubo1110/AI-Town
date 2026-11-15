from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, resolve_player_id
from app.api.schemas.event import EventListOut, EventOut
from app.repos import event_repo

router = APIRouter(prefix="/events", tags=["events"])


#返回事件流
@router.get("", response_model=EventListOut, summary="事件流")
async def list_events(
    # 身份来自签名 Cookie；player_id 只是没有 Cookie 时的兼容回退（见 deps.resolve_player_id）
    player_id: int = Depends(resolve_player_id),
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