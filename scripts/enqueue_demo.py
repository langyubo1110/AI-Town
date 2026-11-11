"""手动投一条消息，验证 worker 管道。"""

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import get_settings
from app.infra.cache import build_redis
from app.worker.streams import publish


async def main() -> None:
    redis = build_redis(get_settings().redis_url)
    msg_id = await publish(
        redis,
        event="npc_chat_requested",
        payload={"npc_a": "张三", "npc_b": "李四", "topic": "多智能体系统怎么设计"},
    )
    print(f"投递成功 id={msg_id}")
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())