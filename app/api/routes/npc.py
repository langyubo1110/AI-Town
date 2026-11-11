"""NPC 相关接口。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.schemas.npc import NPCListOut, NPCOut
from app.repos import npc_repo

router = APIRouter(prefix="/npcs", tags=["npc"])


@router.get("", response_model=NPCListOut, summary="NPC 列表")
async def list_npcs(session: AsyncSession = Depends(get_session)) -> NPCListOut:
    # 1. 调 repo 拿数据 数据库 ORM 对象列表。
    npcs=await npc_repo.list_active(session)
    #把 ORM 对象 n 校验并转换成 NPCOut 这个 Pydantic 模型实例。
    items=[NPCOut.model_validate(n) for n in npcs]
    # 2. 组装成 NPCListOut 返回
    return NPCListOut(total=len(items), items=items)