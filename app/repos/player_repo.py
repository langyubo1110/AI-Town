"""玩家数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player


async def get_or_create_by_name(session: AsyncSession, name: str) -> Player:
    """按名字取玩家，不存在则创建。"""
    player = await session.scalar(select(Player).where(Player.name == name))
    if player is None:
        player = Player(name=name)
        session.add(player)
        await session.flush()      # ★ 关键：拿到自增 id，但【不提交】
        '''
        后面还要用 player.id 去查好感度、还要更新好感度。
        如果现在 commit，事务就结束了——一个请求被拆成多个事务，中途失败会留下半截数据（玩家建了，好感度没建）。
        用 flush 保持在同一事务里，最后统一 commit：要么全成功，要么全回滚。这就是"事务边界"。
        '''
    return player