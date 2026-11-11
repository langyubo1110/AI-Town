"""事件台账的读写。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Event

#写入一条事务
async def create(
    session: AsyncSession,
    *,
    player_id: int,
    npc_id: int | None,
    event_type: str,
    summary: str,
    payload: dict,
) -> Event:
    event = Event(
        player_id=player_id,
        npc_id=npc_id,
        event_type=event_type,
        summary=summary,
        payload=payload,
    )
    #加入session待提交队列
    session.add(event)
    return event

#游标分页读取
async def list_recent(
    session: AsyncSession,
    *,
    player_id: int,
    event_type: str | None = None,
    limit: int = 20,
    before_id: int | None = None,
) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.player_id == player_id)
        .order_by(Event.id.desc())
        .limit(limit)
    )
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if before_id is not None:
        stmt = stmt.where(Event.id < before_id)
    return list(await session.scalars(stmt))