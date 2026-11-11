"""Redis Stream 的常量与基础操作。"""

import json
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)

STREAM = "aitown:events"
GROUP = "aitown-workers"


async def ensure_group(redis: Redis) -> None:
    """幂等创建消费组（已存在就跳过）。"""
    try:
        # id="$" 表示只消费"从现在起新增的消息"
        await redis.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
        log.info("stream_group_created", stream=STREAM, group=GROUP)
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            log.info("stream_group_exists", stream=STREAM, group=GROUP)
            return
        raise


async def publish(redis: Redis, *, event: str, payload: dict[str, Any]) -> str:
    """投递一条消息，返回消息 id。"""
    return await redis.xadd(
        STREAM,
        {
            "event": event,
            # Stream 的 field 只能是字符串，结构体必须自己序列化
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )


def decode(fields: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """把字符串字段还原成 (event, payload)。"""
    event = fields.get("event", "")
    raw = fields.get("payload", "{}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # 脏数据不要炸掉整个 worker
        payload = {"_raw": raw}
    return event, payload