"""小镇事件：让 NPC 之间互动（异步），以及查看 NPC 的今日计划。"""

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import plans
from app.api.deps import get_redis, get_session
from app.api.schemas.town import (
    NpcChatAccepted,
    NpcChatIn,
    NpcPlanOut,
    PlanListOut,
    PlanStepOut,
)
from app.core.clock import local_now
from app.domain import plans as plan_rules
from app.models import Player
from app.repos import npc_repo
from app.worker.streams import publish

router = APIRouter(prefix="/town", tags=["town"])


@router.post(
    "/npc-chat",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=NpcChatAccepted,
    summary="让两个 NPC 聊一会儿（异步处理）",
)
async def npc_chat(
    payload: NpcChatIn,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> NpcChatAccepted:
    if payload.npc_a == payload.npc_b:
        raise HTTPException(status_code=400, detail="不能让同一个 NPC 跟自己聊天")

    # —— 同步校验：所有"能立刻判断对错"的事都在这里做完 ——
    for name in (payload.npc_a, payload.npc_b):
        npc = await npc_repo.get_by_name(session, name)
        if npc is None or not npc.is_active:
            raise HTTPException(status_code=404, detail=f"NPC '{name}' 不存在或已下线")

    if await session.get(Player, payload.player_id) is None:
        raise HTTPException(status_code=404, detail=f"玩家 {payload.player_id} 不存在")

    # —— 异步执行：投一条消息就返回 ——
    task_id = await publish(
        redis,
        event="npc_chat_requested",
        payload={
            "player_id": payload.player_id,
            "npc_a": payload.npc_a,
            "npc_b": payload.npc_b,
            "topic": payload.topic,
            "turns": payload.turns,
        },
    )
    return NpcChatAccepted(task_id=task_id)


@router.get("/plans", response_model=PlanListOut, summary="查看 NPC 今天的计划")
async def list_plans(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> PlanListOut:
    """只读接口：计划由 worker 的 ticker 懒生成，这里不触发写入。"""
    now = local_now()
    npcs = await npc_repo.list_active(session)

    items: list[NpcPlanOut] = []
    for npc in npcs:
        steps = await plans.load_plan(redis, npc_id=npc.id, day=now.date())
        done, total = plan_rules.progress(steps)
        items.append(
            NpcPlanOut(
                npc_id=npc.id,
                npc_name=npc.name,
                done=done,
                total=total,
                steps=[PlanStepOut(**step) for step in steps],
            )
        )

    return PlanListOut(date=now.date().isoformat(), items=items)