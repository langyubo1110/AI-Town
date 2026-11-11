"""Redis 异步客户端。"""

import redis.asyncio as aioredis


def build_redis(url: str, *, socket_timeout: float | None = 3.0) -> aioredis.Redis:
    """创建 Redis 异步客户端。

    socket_timeout 默认 3 秒（适合 API 的短命令）。
    阻塞式命令（XREADGROUP BLOCK）必须传更大的值，否则客户端先超时。
    """
    return aioredis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,   # 连不上 3 秒失败，别挂死
        socket_timeout=socket_timeout,
    )