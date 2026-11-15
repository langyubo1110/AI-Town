"""Redis Stream 的常量与基础操作。"""

import json
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)

STREAM = "aitown:events"
GROUP = "aitown-workers"

# 队列最多保留多少条。超过就按"近似长度"裁剪掉最老的。
# 为什么必须裁：worker 只消费"新"消息（XREADGROUP >），老消息留在 Stream 里
# 没有任何用处，却会一直吃内存 —— 跑一周 Redis 就被撑爆。
# 用 ~ 近似裁剪：Redis 按整个宏节点丢弃，比精确裁剪快得多，多留几条无所谓。
STREAM_MAXLEN = 10_000


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
        maxlen=STREAM_MAXLEN,
        approximate=True,
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