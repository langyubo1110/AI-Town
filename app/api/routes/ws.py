"""WebSocket：把 Redis 频道里的事件转发给浏览器。

为什么需要两个 task：
    pubsub.listen() 是阻塞的 —— 没消息时它一直等，
    如果只有它，客户端断开你也发现不了，连接和 Redis 连接会一直挂着。
    所以必须并行等「Redis 有消息」和「客户端断开」，谁先来算谁。
"""

import asyncio
import contextlib

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.infra.broadcast import channel_for

log = get_logger(__name__)

router = APIRouter()


async def _pump(pubsub, websocket: WebSocket) -> None:
    """Redis → 浏览器。"""
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        await websocket.send_text(message["data"])


async def _watch(websocket: WebSocket) -> None:
    """等客户端断开。收到任何文本都忽略（将来可当心跳用）。"""
    while True:
        await websocket.receive_text()


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket, player_id: int = Query(..., ge=1)) -> None:
    await websocket.accept()

    # pubsub 会从连接池里借一条【独占】连接，订阅期间不能被别的命令复用
    redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    channel = channel_for(player_id)
    await pubsub.subscribe(channel)
    log.info("ws_connected", player_id=player_id)

    pump = asyncio.create_task(_pump(pubsub, websocket))
    watch = asyncio.create_task(_watch(websocket))

    try:
        done, _pending = await asyncio.wait(
            {pump, watch}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                log.warning(
                    "ws_task_error",
                    player_id=player_id,
                    error=type(exc).__name__,
                    detail=str(exc)[:200],
                )
    finally:
        for task in (pump, watch):
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        log.info("ws_closed", player_id=player_id)