"""对话接口（LangGraph 版）。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.api.deps import get_redis, get_session
from app.agents.graph import get_chat_graph
from app.api.schemas.chat import ChatIn, ChatOut, ToolUsed
from app.domain import affinity_rules
from app.agents.runtime import build_config
from app.infra.broadcast import publish_event
from app.domain.exceptions import NPCNotFoundError

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatOut, summary="与 NPC 对话")
#getssion:打开事务
async def chat(payload: ChatIn, session: AsyncSession = Depends(get_session),redis: Redis = Depends(get_redis),) -> ChatOut:
    graph = get_chat_graph()
    # thread_id 编码了"谁和谁在聊"，同一对玩家+NPC 复用同一个会话
    thread_id = f"p:{payload.player_name}|n:{payload.npc_name}"
    config = build_config(
        session=session,
        redis=redis,
        thread_id=thread_id,
        user_id=payload.player_name,
    )
    try:
       #response响应
       final=await graph.ainvoke(
           {
               "player_name": payload.player_name,
               "npc_name": payload.npc_name,
               "message": payload.message,
               # "session": session,
               # "redis": redis,
           },
           config=config
       )
    except NPCNotFoundError as exc:
        # 领域异常 → HTTP 语义（路由层负责翻译）
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # 图里只把「待广播」放进 state，真正的推送放在这里：
    # 此刻 persist 已经 commit，推出去的事件一定能在数据库查到
    pending = final.get("pending_broadcast")
    if pending:
        await publish_event(redis, player_id=final["player_id"], event=pending)

    return ChatOut(
        player_id=final["player_id"],
        npc_name=payload.npc_name,
        npc_title=final["npc_title"],     # ← 由 load_context 写进 state
        reply=final["reply"],
        affinity_score=final["affinity_score"],
        affinity_delta=final["delta"],
        affinity_level=affinity_rules.level_from_score(final["affinity_score"]),
        # 只暴露"用了什么工具"，不返回工具结果（可能很长，且属于内部细节）
        tools=[
            ToolUsed(
                name=str(step["call"].get("name", "")),
                args=step["call"].get("args") or {},
            )
            for step in (final.get("tool_trace") or [])
        ],
    )