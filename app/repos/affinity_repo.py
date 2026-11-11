"""好感度数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.affinity_rules import DEFAULT_SCORE
from app.models import Affinity



async def get_or_create(session: AsyncSession, player_id: int, npc_id: int) -> Affinity:
    """取好感度记录，不存在则以默认值创建。"""
    stmt = select(Affinity).where(
        Affinity.player_id == player_id,
        Affinity.npc_id == npc_id,
    )
    affinity = await session.scalar(stmt)
    if affinity is None:
        affinity = Affinity(player_id=player_id, npc_id=npc_id, score=DEFAULT_SCORE)
        session.add(affinity)
        await session.flush()
    return affinity
