"""对话接口（LangGraph 版）。

两个入口，共用同一张图：
    POST /api/chat          一次性返回（默认形态，也是前端降级用）
    POST /api/chat/stream   SSE 流式（先吐字，最后一条补元数据）
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import get_chat_graph
from app.agents.runtime import build_config
from app.api.deps import get_redis, get_session
from app.api.schemas.chat import ChatIn, ChatOut, ToolUsed
from app.domain import affinity_rules
from app.domain.exceptions import NPCNotFoundError
from app.infra.broadcast import publish_event

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    """一条 SSE 帧。`data: ` 前缀和结尾两个换行都是协议硬要求。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

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


@router.post("/stream", summary="与 NPC 对话（SSE 流式）")
async def chat_stream(
    payload: ChatIn,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
):
    """流式对话。

    事件序列（每帧都是 `data: {json}`）：
        {"type":"delta","text":"前端逐字追加的内容"}
        {"type":"error","message":"..."}          —— 找不到 NPC 时
        {"type":"done", ...ChatOut 的全部字段}    —— 最后一条

    为什么元数据放最后：好感度是整轮结束才由 analyze_turn 算出来的，
    流式过程中根本还不存在。前端先渲染文字，收到 done 再补分数和工具标签。
    """
    graph = get_chat_graph()
    thread_id = f"p:{payload.player_name}|n:{payload.npc_name}"
    config = build_config(
        session=session,
        redis=redis,
        thread_id=thread_id,
        user_id=payload.player_name,
    )
    inputs = {
        "player_name": payload.player_name,
        "npc_name": payload.npc_name,
        "message": payload.message,
    }

    async def event_stream():
        try:
            # astream_events 会把"图里每个节点内部的每次模型调用"都抛出来。
            # 我们只要 agent_step 的 token —— analyze_turn 也在调模型，
            # 不按节点过滤的话，好感度分析的文字会混进回复里。
            async for event in graph.astream_events(inputs, config=config, version="v2"):
                if event.get("event") != "on_chat_model_stream":
                    continue
                if (event.get("metadata") or {}).get("langgraph_node") != "agent_step":
                    continue

                chunk = (event.get("data") or {}).get("chunk")
                if chunk is None:
                    continue
                # 这一轮模型决定调工具：先不吐字，等工具结果再重说
                if getattr(chunk, "tool_call_chunks", None):
                    continue

                text = getattr(chunk, "content", "") or ""
                if text:
                    yield _sse({"type": "delta", "text": text})
        except NPCNotFoundError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return

        # 图跑完了，取终态补齐元数据
        snapshot = await graph.aget_state(config)
        final = dict(snapshot.values or {})

        pending = final.get("pending_broadcast")
        if pending and final.get("player_id"):
            # 和 /api/chat 同一条规矩：persist 已 commit，此时推出去的事件一定查得到
            await publish_event(redis, player_id=final["player_id"], event=pending)

        score = final.get("affinity_score", 0.0)
        yield _sse(
            {
                "type": "done",
                "player_id": final.get("player_id"),
                "npc_name": payload.npc_name,
                "npc_title": final.get("npc_title", ""),
                "reply": final.get("reply", ""),
                "affinity_score": score,
                "affinity_delta": final.get("delta", 0.0),
                "affinity_level": affinity_rules.level_from_score(score),
                "tools": [
                    {
                        "name": str(step["call"].get("name", "")),
                        "args": step["call"].get("args") or {},
                    }
                    for step in (final.get("tool_trace") or [])
                ],
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx 默认会缓冲上游响应，不加这一条 SSE 会被攒到最后一次性吐出
            "X-Accel-Buffering": "no",
        },
    )