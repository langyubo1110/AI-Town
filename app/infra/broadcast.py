"""事件广播：把「发生了什么」推给订阅者（Redis Pub/Sub）。"""

import json

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)


def channel_for(player_id: int) -> str:
    """每个玩家一个频道：只推给自己的连接。"""
    return f"aitown:events:player:{player_id}"


async def publish_event(redis: Redis, *, player_id: int, event: dict) -> None:
    """把一条事件广播出去。

    注意：调用方必须保证【数据库已经 commit】。
    """
    try:
        receivers = await redis.publish(
            channel_for(player_id),
            json.dumps(event, ensure_ascii=False, default=str),
        )
        # receivers = 有几个订阅者收到；0 表示前端还没连上（排障用）
        log.info(
            "event_broadcast",
            player_id=player_id,
            receivers=receivers,
            evt=event.get("event_type"),
        )
    except Exception as exc:
        # 推送失败不该让业务失败：前端还有轮询兜底
        log.warning(
            "broadcast_failed",
            player_id=player_id,
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )