"""NPC 数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NPC


async def list_active(session: AsyncSession) -> list[NPC]:
    """查询所有启用的 NPC。"""
    #构造查询语句
    stmt=select(NPC).where(NPC.is_active.is_(True)).order_by(NPC.id)
    #查询数据库
    result=await session.scalars(stmt)
    return list(result.all())

async def get_by_name(session: AsyncSession, name: str) -> NPC | None:
    """按名字查单个 NPC。"""
    stmt=select(NPC).where(NPC.name == name)
    result=await session.scalar(stmt)
    return result